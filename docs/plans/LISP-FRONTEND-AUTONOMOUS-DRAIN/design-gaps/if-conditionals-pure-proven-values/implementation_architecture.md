# `if` Conditionals For Pure Or Already-Proven Values Implementation Architecture

## Scope

This design gap covers only the bounded Workflow Lisp conditional-expression
slice selected by the current drain state:

- add one public `(if condition then-expr else-expr)` expression surface to the
  frontend AST;
- typecheck conditional expressions so the condition is pure, Bool-typed, and
  does not invent new variant-proof rules;
- lower supported `if` expressions through the existing shared authored
  `if`/`then`/`else` workflow surface and the existing Core AST `CoreIf`
  substrate;
- reuse the existing branch-output projection machinery so conditional results
  can flow through `let*`, workflow returns, procedure bodies, and loop bodies;
- add focused fixtures, diagnostics, and regression coverage proving the new
  surface composes with the current typechecker, helper normalization,
  lowering, source maps, and shared validation.

Out of scope for this tranche:

- a general boolean-expression language such as `and`, `or`, `not`, comparison
  operators, or user-authored predicate combinators;
- proof creation from arbitrary boolean tests, enum comparisons, or status
  strings;
- omitted-else `if`, `cond`, multi-branch conditionals, or `nil`/unit typing;
- new command adapters, runtime-native branching effects, or changes to shared
  provider/command execution;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  SourceMap, pointer authority, or variant proof.

This is an implementation architecture for exactly the selected
`if-conditionals-pure-proven-values` gap. It does not reopen the broader
frontend or runtime design.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_frontend_specification.md`
  - `12. Conditionals`
  - `44. Typed Frontend AST`
  - `45. Core Workflow AST`
  - `53. match Lowering`
  - `59. Validation Sequence`
  - `60. Type Validation`
  - `63. Variant Proof Validation`
  - `74. Source Map Requirements`
  - `92. Required Lints`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `4.3 Expressions`
  - `9. Source Spans And Diagnostics`
  - `10. Validation`
  - `14. Implementation Stages`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/steering.md`

The slice must also preserve the guardrails established by the current checkout
and prior implementation architectures:

- keep `orchestrator/workflow_lisp/` as the frontend-owned package and keep
  shared runtime semantics under `orchestrator/workflow/`;
- reuse the staged frontend pipeline:
  read -> syntax -> modules -> macro expansion -> definitions/functions/
  procedures/workflows -> typecheck/effects -> lowering -> shared validation;
- reuse `SourcePosition`, `SourceSpan`, recursive syntax provenance,
  `LispFrontendDiagnostic`, `EffectSummary`, `LoweringOriginMap`, and the
  persisted `source_map.json` bridge rather than inventing parallel tracking
  systems;
- reuse the existing shared authored branch substrate:
  `SurfaceStepKind.IF`,
  `SurfaceBranchBlock`,
  typed predicates,
  `CoreIf`,
  and existing runtime branch execution;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- keep command boundaries governed by the existing `external_tool` versus
  `certified_adapter` contract and do not let conditional lowering become a
  loophole for hidden shell/Python semantics.

`docs/design/workflow_command_adapter_contract.md` is authoritative here
because `if` branches may contain existing command-backed expressions such as
`command-result`, `resume-or-start`, or `resource-transition`. This slice must
not introduce:

- condition-evaluation steps implemented by inline shell or Python glue;
- report parsing to decide branches;
- pointer-file reads as branch authority;
- hidden command rewrites that bypass existing typed adapter or external-tool
  boundaries.

`docs/steering.md` is empty in this checkout. That does not widen scope. The
selector bundle, architecture target contract, prior implementation
architectures, and current repo evidence remain the effective steering
surfaces.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

Reviewed the index-listed architecture corpus, with direct dependency on:

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/core-workflow-ast-shared-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defun-pure-helper-surface/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-validation-diagnostics-pipeline/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/loop-recur-bounded-loops/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`

### Decisions Reused

- Reuse the existing staged frontend pipeline and package ownership split.
- Reuse Stage 2/Stage 4 expression typing and proof rules:
  variant proof is created by `match`, remains explicit, and is not recreated
  by generic conditionals.
- Reuse the shared authored branch substrate instead of inventing a
  frontend-only conditional executor.
- Reuse the existing branch-output projection style from `match` and
  `loop/recur`, including `output_refs`, branch `outputs`, and generated
  projection-anchor steps where needed.
- Reuse the `defun` slice's pure-helper normalization path so helper calls
  inside conditional conditions or branches normalize through the existing
  frontend-only pure-expression flow.
- Reuse existing source-map coverage and nested-branch traversal instead of
  changing the source-map schema.

### New Decisions In This Slice

- Add a dedicated frontend `IfExpr` node and a minimal condition-shape model
  for Bool literals and Bool-valued references.
- Keep `if` as a normal expression form whose branches may be effectful, while
  the condition itself must remain pure.
- Make `if` inherit the current proof scope into both branches unchanged.
  Conditions do not create new proof facts.
- Keep the author-facing condition subset deliberately small in this slice:
  only pure Bool literals and Bool-valued local refs/field refs are eligible
  for lowering to shared typed predicates.
- Extend loop-body lowering so existing public `loop/recur` bodies can use
  `if` without changing the loop runtime contract.

### Conflicts Or Revisions

The typed-expression slice originally centered the public expression language on
`let*`, `match`, record construction, field access, and literals. This slice
revises that surface narrowly:

- `if` becomes an admitted expression form;
- the proof model is not revised to treat `if` as a proof-producing construct;
- existing `match` remains the only frontend form that narrows union variants.

The loop/recur slice documented a generated shared `if` step inside loop-state
routing but did not expose authored `if`. This slice narrows that gap:

- authored `if` now reuses the same shared branch substrate that loop lowering
  already proves viable;
- no shared runtime branch semantics are changed.

No prior slice is revised on shared concepts such as spans, diagnostics, Core
Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority,
or variant proof.

## Ownership Boundaries

This slice owns:

- frontend AST/elaboration for authored `if`;
- frontend-local condition-shape classification for pure Bool literals and
  Bool-valued refs;
- typechecking rules for Bool conditions, branch-type compatibility, purity of
  the condition, and proof-scope inheritance;
- lowering of `IfExpr` into shared authored `if` steps plus branch outputs;
- extensions to helper normalization and other expression walkers so `if`
  participates in existing pure-helper, lowering, and traversal logic;
- focused tests for syntax, typechecking, lowering, loop integration, helper
  normalization, and source-map lineage.

This slice intentionally does not own:

- a general boolean predicate language or new shared typed-predicate operators;
- new proof rules, variant narrowing by equality tests, or status-string gates;
- runtime execution semantics for shared `if` steps;
- new command adapters, legacy adapters, or runtime-native branching effects;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  SourceMap, pointer authority, or workflow-call transport.

## Current Checkout Facts

The current checkout already contains the shared runtime substrate needed for
branching, but not the selected frontend surface:

- `orchestrator/workflow_lisp/expressions.py` defines `LetStarExpr`,
  `MatchExpr`, `LoopRecurExpr`, `FunctionCallExpr`, phase/resource/drain forms,
  and effectful structured-result forms, but there is no `IfExpr`.
- `_elaborate_list(...)` in `expressions.py` recognizes `record`, `let*`,
  `match`, `loop/recur`, `call`, `provider-result`, `command-result`, and the
  current stdlib forms, but not `if`.
- `orchestrator/workflow_lisp/typecheck.py` builds proof facts only for
  `MatchExpr`; there is no conditional case and therefore no condition purity
  or branch-type rule.
- `orchestrator/workflow_lisp/functions.py` already normalizes pure helper
  calls and traverses the concrete expression union; introducing `IfExpr`
  without extending those traversals would silently skip condition and branch
  bodies.
- `orchestrator/workflow_lisp/lowering.py` already lowers generated shared
  `if` steps internally for loop-state routing, already uses `_TerminalResult`
  with `output_kind="if"`, and already traverses nested `if` statements in
  source-map helpers.
- shared authored/runtime surfaces already support conditional branching via
  `SurfaceStepKind.IF`, `SurfaceStep.if_condition`, `SurfaceBranchBlock`,
  `parse_typed_predicate(...)`, and `orchestrator/workflow/core_ast.py:CoreIf`.
- there are currently no authored Workflow Lisp fixtures or tests covering an
  `if` expression surface in helpers, workflows, procedures, or loop bodies.

This slice should add only the missing frontend expression contract and reuse
the existing shared branch substrate.

## Proposed Package Boundary

Extend the current frontend package with one small conditional helper and
targeted updates to the existing expression, typing, normalization, and
lowering layers:

```text
orchestrator/workflow_lisp/
  __init__.py
  conditionals.py      # new condition-shape classifier + predicate lowering
  expressions.py
  functions.py
  lowering.py
  typecheck.py
tests/
  test_workflow_lisp_expressions.py
  test_workflow_lisp_variant_proofs.py
  test_workflow_lisp_functions.py
  test_workflow_lisp_lowering.py
  test_workflow_lisp_diagnostics.py
  test_workflow_lisp_loop_recur.py
  fixtures/workflow_lisp/valid/if_conditionals_minimal.orc
  fixtures/workflow_lisp/valid/if_conditionals_loop_body.orc
  fixtures/workflow_lisp/invalid/if_condition_not_bool.orc
  fixtures/workflow_lisp/invalid/if_condition_effectful.orc
  fixtures/workflow_lisp/invalid/if_condition_not_projectable.orc
  fixtures/workflow_lisp/invalid/if_variant_proof_missing.orc
```

Responsibilities:

- `conditionals.py`
  - define the minimal condition-shape model for this slice;
  - classify typed condition expressions into a lowerable shape or a frontend
    diagnostic;
  - render the lowerable shape into shared authored predicate mappings.
- `expressions.py`
  - elaborate `(if condition then-expr else-expr)` into `IfExpr`;
  - reject malformed arity before typing.
- `typecheck.py`
  - typecheck conditions and branches;
  - enforce condition purity and branch-type compatibility;
  - preserve proof scope without adding new proof facts.
- `functions.py`
  - descend through `IfExpr` in helper purity validation, dependency analysis,
    and pure-call normalization.
- `lowering.py`
  - lower `IfExpr` to a shared authored `if` step plus branch outputs;
  - extend loop-body lowering and local-type resolution utilities to recognize
    `IfExpr`.
- `__init__.py`
  - export `IfExpr` and any new condition helper types needed by tests.

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/spans.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/source_map.py`
- shared authored/core/runtime modules under `orchestrator/workflow/`

## Data Model

### Frontend Expression Node

Add one new expression node:

```text
IfExpr(
  condition_expr,
  then_expr,
  else_expr,
  span,
  form_path,
  expansion_stack,
)
```

Design rules:

- `IfExpr` is always ternary in this slice;
- the condition, then branch, and else branch remain ordinary `ExprNode`
  children;
- spans and form paths point at the authored `if` form, not only one child.

### Minimal Condition Shape

Add one frontend-local condition-shape layer, deliberately smaller than the
shared predicate AST:

- `LiteralBoolCondition(value: bool)`
- `BoolRefCondition(base_name: str, fields: tuple[str, ...])`

Why this extra layer exists:

- the shared runtime already owns typed predicate execution;
- the frontend needs one minimal, typed, source-mapped contract for deciding
  whether a Workflow Lisp condition can lower honestly into that shared
  substrate;
- the selected gap does not authorize a user-facing predicate language.

This slice intentionally does not add frontend condition shapes for:

- boolean negation;
- conjunction/disjunction;
- ordered comparisons;
- enum or variant equality tests;
- report- or pointer-derived booleans.

## Author-Facing Surface

The public authored form is:

```lisp
(if condition then-expr else-expr)
```

Allowed condition shape in this slice:

- a Bool literal such as `true` or `false`;
- a Bool-valued bound name;
- a Bool-valued dotted field access whose variant-specific access is already
  proved by an enclosing `match`.

Examples that are valid in scope:

```lisp
(if selected.active?
  (resource-transition ...)
  selected)
```

```lisp
(match attempt
  ((BLOCKED blocked)
    (if blocked.retryable
      blocked
      blocked))
  ((COMPLETED completed)
    completed))
```

Examples intentionally still rejected by this slice:

```lisp
(if (= implementation.state COMPLETED) ...)
```

```lisp
(if (command-result probe :argv ("python" "probe.py") :returns ProbeResult) ...)
```

`match` remains the required mechanism for variant proof and variant routing.
`if` is only for pure or already-proven Bool values.

## Typechecking And Proof Model

### Condition Rules

Typechecking of `IfExpr` proceeds in this order:

1. typecheck `condition_expr`;
2. require the condition type to be exactly `Bool`;
3. require the condition effect summary to be empty;
4. classify the typed condition into one of the supported condition shapes;
5. typecheck `then_expr` and `else_expr` under the inherited lexical
   environment and inherited proof scope;
6. require the two branch result types to match exactly.

This yields the following user-visible guarantees:

- conditions cannot call providers, commands, workflows, procedures, or
  adapter-backed stdlib forms;
- conditions cannot hide semantic command behavior behind pure-looking helper
  syntax;
- branches may remain effectful, but the condition itself cannot.

### Proof Rules

`if` does not create proof.

Branch typing must inherit the current `ProofScope` unchanged:

- if an enclosing `match` already proved `attempt == BLOCKED`, both branches
  may use `attempt.progress_report`;
- the condition itself does not prove that a union is in one variant or
  another;
- rejected patterns continue to use the existing proof diagnostics:
  `variant_ref_unproved` and `variant_ref_wrong_variant`.

This keeps the frontend aligned with the full design rule that generic
conditionals must not recreate unproved variant access by status comparisons.

### Effect Summary

The typed `IfExpr` effect summary is:

- empty for the condition, by rule;
- the merged effect summary of both branches for the expression as a whole.

This matches the current `match` treatment: static effect accounting must
include all branch-local effects that may occur at runtime.

## Lowering Model

### Condition Lowering

Condition lowering reuses the shared typed-predicate surface and stays within
the minimal condition shapes defined above:

- `LiteralBoolCondition(true)` lowers to a shared literal compare predicate
  that always evaluates true;
- `LiteralBoolCondition(false)` lowers to a shared literal compare predicate
  that always evaluates false;
- `BoolRefCondition(...)` lowers to an `artifact_bool` predicate against the
  already-lowered shared ref.

This slice deliberately does not lower authored conditions into new shared
predicate operators. Unsupported Bool expressions fail as
`if_condition_not_projectable`.

### General Branch Lowering

Lower `IfExpr` through one generated authored `if` step:

```text
if:
  <typed predicate>
then:
  steps: <lowered then branch>
  outputs: <branch outputs projected from then terminal>
else:
  steps: <lowered else branch>
  outputs: <branch outputs projected from else terminal>
```

The lowering should reuse the same result-type support already exercised by
`match`, workflow returns, and `loop/recur`:

- `PrimitiveTypeRef`
- `PathTypeRef`
- `RecordTypeRef`
- `UnionTypeRef`

No new runtime transport is introduced for `Json`, lists, maps, or other
non-projectable types.

Implementation detail:

- generalize the existing match-branch projection helpers so `if` and `match`
  share one branch-output projection path where practical;
- return an `_TerminalResult` with `output_kind="if"` and ordinary
  `output_refs` so `let*` bindings and return projection continue to work
  without special-case runtime behavior.

### Loop-Body Integration

Existing `loop/recur` bodies currently lower through a restricted expression
subset. This slice extends `_lower_loop_body_expr(...)` so one loop body may
use `IfExpr` when both branches lower to the existing loop-frame output
contract.

That means:

- `continue`/`done` remain the only terminal loop-control forms;
- `if` becomes a router between already-supported terminal/body shapes;
- no cross-iteration proof, accumulator, or exhaustion semantics change.

## Shared Workflow Handoff And Source Maps

This slice reuses shared authored/core/runtime branching surfaces rather than
adding new shared contracts:

- authored lowering targets `SurfaceStepKind.IF`;
- shared authored elaboration already produces `SurfaceStep.if_condition`,
  `then_branch`, and `else_branch`;
- Core AST already exposes `CoreIf`;
- source-map traversal already visits nested `if` statements in both authored
  and Core AST lineage.

Source-map obligations in this slice:

- the generated statement step id for the conditional routes back to the
  authored `IfExpr` span;
- generated branch block ids and any projection-anchor steps also route back to
  the same `IfExpr` origin;
- steps generated inside `then_expr` or `else_expr` preserve their own child
  expression provenance.

No source-map schema change is required. The current source-map/runtime-lineage
surfaces already understand nested `if` statements.

## Diagnostics

Add the minimum new frontend diagnostics required by this slice:

- `if_form_invalid`
  - malformed arity or list shape during elaboration
- `if_condition_not_bool`
  - condition did not resolve to `Bool`
- `if_condition_has_effect`
  - condition attempted to use an effectful expression
- `if_condition_not_projectable`
  - condition was Bool-typed and pure but cannot lower to the minimal shared
    predicate subset owned by this slice

Reuse existing diagnostics where they already express the right failure:

- `type_mismatch` for branch result mismatches
- `variant_ref_unproved`
- `variant_ref_wrong_variant`
- `workflow_return_not_exportable` when a branch result type cannot pass
  through existing lowering/projectability rules

Validation-pass ownership:

- elaboration shape errors remain frontend `type`/syntax-surface diagnostics;
- condition purity and Bool typing are frontend `type` diagnostics;
- projectability may be emitted during typechecking or lowering-surface
  validation, but the code must remain deterministic and frontend-owned;
- shared validation remains authoritative only after authored `if` steps have
  been lowered.

## Test Strategy

Add targeted coverage in the existing frontend test surface:

- `tests/test_workflow_lisp_expressions.py`
  - elaboration of ternary `if`
  - malformed arity
  - exact-bound-name versus field-access conditions
- `tests/test_workflow_lisp_variant_proofs.py`
  - proof inheritance into both `if` branches
  - no proof creation from `if` conditions
- `tests/test_workflow_lisp_functions.py`
  - pure-helper normalization through condition and branch bodies
  - helper dependency walking through `IfExpr`
- `tests/test_workflow_lisp_lowering.py`
  - lowering of Bool-literal conditions
  - lowering of Bool-ref conditions to shared `if`
  - branch output projection for record and union results
  - `let*` bindings from conditional terminals
- `tests/test_workflow_lisp_loop_recur.py`
  - `if` inside authored loop bodies using existing `continue`/`done` terminals
- `tests/test_workflow_lisp_diagnostics.py`
  - diagnostic classification and serialization for the new `if_*` codes

Add fixtures:

- valid minimal workflow fixture with `if` returning a relpath or record
- valid loop-body fixture with `if` around `continue`/`done`
- invalid non-Bool condition fixture
- invalid effectful-condition fixture
- invalid Bool-but-unprojectable condition fixture
- invalid variant-proof-missing fixture

## Implementation Sequence

1. Add `IfExpr` elaboration and exports in `expressions.py` and `__init__.py`.
2. Add `conditionals.py` with the minimal condition-shape model.
3. Extend `typecheck.py` for condition typing, purity, projectability, and
   branch result compatibility.
4. Extend `functions.py` traversals and pure-call normalization to descend
   through `IfExpr`.
5. Extend `lowering.py` for general `IfExpr` lowering and loop-body support.
6. Add fixtures and targeted tests for expressions, proofs, helpers, lowering,
   diagnostics, and loops.
7. Run narrow pytest selectors first, then the small cross-module regression
   set recorded in the implementation plan.

## Acceptance Conditions

- authored Workflow Lisp accepts `(if condition then-expr else-expr)` as a
  frontend expression form;
- conditions must be pure and Bool-typed;
- conditions lower only from the bounded pure/already-proven shape owned by
  this slice;
- `if` does not create new proof facts;
- branches may remain effectful and their effects are included in the typed
  effect summary;
- lowered conditionals use the existing shared `if`/`then`/`else` workflow
  surface and existing `CoreIf` lineage;
- conditional results can flow through `let*`, workflow/procedure returns, and
  loop bodies through existing branch-output projection helpers;
- no new command adapter, inline command glue, runtime-native effect, or
  report/pointer authority surface is introduced.

## Verification Plan

Record deterministic implementation checks in:

`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-full-restart-20260523T081550Z/iterations/8/design-gap-architect/check_commands.json`

The eventual implementation checks should cover:

- collect-only on any new or renamed conditional test modules;
- targeted expression/proof/helper/lowering/loop tests for `if`;
- at least one lowering-path test that proves shared authored `if` output
  projection and source-map lineage remain intact.
