# If Conditionals For Pure Or Already-Proven Values Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the authored Workflow Lisp ternary `if` expression so pure or already-proven `Bool` conditions can route existing effectful expressions through the shared branch substrate without changing proof authority, runtime semantics, or command-boundary policy.

**Architecture:** Keep ownership inside `orchestrator/workflow_lisp/` and reuse the current read -> syntax -> modules -> macro expansion -> definitions/functions/procedures/workflows -> typecheck -> lowering -> shared-validation seam. Add one frontend-local `IfExpr` plus a minimal condition classifier in `conditionals.py`, typecheck conditions and branches without creating proof, then lower authored conditionals through the existing shared authored/core `if` substrate and the existing branch-output projection machinery already used by `match` and `loop/recur`.

**Tech Stack:** Python 3 dataclasses, the existing `orchestrator.workflow_lisp` compiler/typecheck/lowering stack, shared authored/core workflow branch support under `orchestrator/workflow/`, pytest, and `.orc` fixtures under `tests/fixtures/workflow_lisp/`.

---

## Fixed Inputs

Treat these files as implementation authority for this slice:

- `docs/index.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - Section 12 (`if` allowed only for pure or already-proven values)
  - Section 44 (typed frontend AST)
  - Section 53 (`match` lowering and proof context)
  - Sections 59-63 (validation, type validation, variant proof validation)
  - Section 74 (source-map requirements)
  - Section 92 (required lints; no new lint work in this slice)
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - Section 4.3 (expression surface)
  - Sections 9, 10, and 14 (diagnostics, validation, staged implementation)
- `docs/design/workflow_language_design_principles.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/steering.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-full-restart-20260523T081550Z/iterations/8/design-gap-architect/work_item_context.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/if-conditionals-pure-proven-values/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-full-restart-20260523T081550Z/iterations/8/design-gap-architect/check_commands.json`

Current checkout facts that should not be rediscovered during execution:

- `docs/steering.md` is empty in this checkout, so it does not widen scope.
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` has no events.
- `orchestrator/workflow_lisp/expressions.py` already supports `let*`, `match`, `loop/recur`, provider/command results, procedures, workflows, and stdlib forms, but has no authored `IfExpr` and no `if` branch in `_elaborate_list(...)`.
- `orchestrator/workflow_lisp/typecheck.py` already carries `ProofScope`, uses `_unify_loop_control_types(...)` for branch convergence, and resets proof inside `loop/recur`, but has no authored conditional case.
- `orchestrator/workflow_lisp/functions.py` already normalizes helper calls and walks the concrete expression union, so adding `IfExpr` without updating those traversals would silently miss conditions and branches.
- `orchestrator/workflow_lisp/lowering.py` already:
  - lowers generated/shared branching for loops and matches;
  - uses `_TerminalResult` with `output_kind="if"` in existing internal paths;
  - has `_render_boolean_predicate(...)` for current Bool guard rendering;
  - has `_lower_loop_body_expr(...)` restricted to `let*`, `match`, `continue`, and `done`;
  - has `_resolve_inline_expr_value(...)`, `_binding_type_for_expr(...)`, and `_resolve_lowering_expr_type(...)` as the existing lowering-time expression seams.
- Shared authored/core/runtime code already supports `SurfaceStepKind.IF`, `SurfaceBranchBlock`, `if_condition`, `parse_typed_predicate(...)`, and `CoreIf`.

## Hard Scope Limits

Implement only this bounded conditional-expression slice:

- public authored `(if condition then-expr else-expr)` elaboration;
- condition typing requiring exact `Bool`, purity, and frontend-owned projectability;
- proof-scope inheritance into both branches without creating new proof facts;
- lowering through shared authored `if`/`then`/`else` plus projected branch outputs;
- loop-body support so `if` can route between existing `continue`/`done` forms;
- focused fixtures and tests for syntax, proofs, helper normalization, lowering, diagnostics, and loop integration.

Explicit non-goals:

- no general boolean algebra (`and`, `or`, `not`, comparisons, user predicates);
- no enum/variant equality tests or status-string gates;
- no proof creation from `if`;
- no omitted-else `if`, `cond`, or multi-branch routing;
- no new shared predicate operators, command adapters, runtime-native branching effects, or pointer/report authority changes;
- no new lint implementation in this slice;
- no YAML generation, new semantic IR layer, or runtime redesign.

## File Ownership

Create:

- `orchestrator/workflow_lisp/conditionals.py`
- `tests/fixtures/workflow_lisp/valid/if_conditionals_minimal.orc`
- `tests/fixtures/workflow_lisp/valid/if_conditionals_loop_body.orc`
- `tests/fixtures/workflow_lisp/invalid/if_condition_not_bool.orc`
- `tests/fixtures/workflow_lisp/invalid/if_condition_effectful.orc`
- `tests/fixtures/workflow_lisp/invalid/if_condition_not_projectable.orc`
- `tests/fixtures/workflow_lisp/invalid/if_variant_proof_missing.orc`

Modify:

- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/functions.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/__init__.py`
- `tests/test_workflow_lisp_expressions.py`
- `tests/test_workflow_lisp_variant_proofs.py`
- `tests/test_workflow_lisp_functions.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_diagnostics.py`
- `tests/test_workflow_lisp_loop_recur.py`

Reuse without widening ownership:

- `orchestrator/workflow_lisp/spans.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/source_map.py`
- shared authored/core/runtime branch code under `orchestrator/workflow/`

Do not modify unless a focused failing test proves it is necessary:

- `orchestrator/workflow/predicates.py`
- `orchestrator/workflow/core_ast.py`
- `orchestrator/workflow/surface_ast.py`
- other CLI/runtime/demo workflow code

## Required Behavioral Contract

Keep these rules fixed while implementing:

- `if` is always ternary in this slice.
- The condition must typecheck to exact `Bool`.
- The condition must be pure: no provider, command, workflow, procedure, stdlib adapter, or loop effects.
- Supported lowerable condition shapes are only:
  - `true` / `false`
  - a Bool-valued bound name
  - a Bool-valued dotted field access that is already legal under inherited proof
- `if` inherits the current `ProofScope` into both branches unchanged.
- `if` does not create proof; only `match` remains proof-producing.
- Branch result types must agree exactly, except that loop-body branch results may reuse the existing `_unify_loop_control_types(...)` convergence behavior already used by `match`.
- The expression effect summary is the merged effect summary of both branches; the condition contributes no effects by rule.
- Lowering must reuse shared typed predicates and shared branch execution, not inline shell/Python glue.
- Conditional results must continue to flow through existing `_TerminalResult`, `let*` binding, output projection, and loop-frame projection mechanics.

New frontend diagnostics required by this slice:

- `if_form_invalid`
- `if_condition_not_bool`
- `if_condition_has_effect`
- `if_condition_not_projectable`

Reuse existing diagnostics where appropriate:

- `type_mismatch`
- `variant_ref_unproved`
- `variant_ref_wrong_variant`
- `workflow_return_not_exportable`

## Concrete Shape To Implement

Frontend expression node in `orchestrator/workflow_lisp/expressions.py`:

```python
@dataclass(frozen=True)
class IfExpr:
    condition_expr: "ExprNode"
    then_expr: "ExprNode"
    else_expr: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()
```

Minimal condition model in `orchestrator/workflow_lisp/conditionals.py`:

```python
@dataclass(frozen=True)
class LiteralBoolCondition:
    value: bool


@dataclass(frozen=True)
class BoolRefCondition:
    base_name: str
    fields: tuple[str, ...]


ConditionShape = LiteralBoolCondition | BoolRefCondition
```

Implement the helper surface so both typechecking and lowering call the same classifier:

```python
def classify_condition_expr(expr: ExprNode, *, type_ref: TypeRef) -> ConditionShape: ...
def render_condition_predicate(shape: ConditionShape, *, local_values: Mapping[str, Any]) -> dict[str, Any]: ...
```

Implementation notes:

- Keep the condition classifier frontend-local. Do not add fields to shared predicate AST types.
- Do not widen `TypedExpr` just to cache condition shape. Re-run the shared classifier in lowering if needed so this remains a small, local slice.
- `render_condition_predicate(...)` should lower:
  - `LiteralBoolCondition(True|False)` to the existing `compare == True` predicate form;
  - `BoolRefCondition(...)` to `artifact_bool` against the already-resolved shared ref.

## Task 1: Lock The Public Conditional Surface With Fixtures And Failing Tests

**Files:**

- Create: `tests/fixtures/workflow_lisp/valid/if_conditionals_minimal.orc`
- Create: `tests/fixtures/workflow_lisp/valid/if_conditionals_loop_body.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/if_condition_not_bool.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/if_condition_effectful.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/if_condition_not_projectable.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/if_variant_proof_missing.orc`
- Modify: `tests/test_workflow_lisp_expressions.py`
- Modify: `tests/test_workflow_lisp_variant_proofs.py`
- Modify: `tests/test_workflow_lisp_functions.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`
- Modify: `tests/test_workflow_lisp_loop_recur.py`

- [ ] **Step 1: Add valid fixtures that lock both ordinary and loop-body `if` usage**

Create:

- `if_conditionals_minimal.orc`
  - one workflow returning a relpath or record via `(if ready report-path fallback-path)` or a record-wrapping equivalent;
  - include one Bool input or Bool record field so lowering can use a ref-backed predicate.
- `if_conditionals_loop_body.orc`
  - one `loop/recur` body where `if` routes to `continue` in one branch and `done` in the other.

Use only existing externs and command-boundary shapes already used by nearby tests.

- [ ] **Step 2: Add invalid fixtures for each new diagnostic or proof boundary**

Create fixtures that fail for:

- non-Bool condition;
- effectful condition such as `provider-result` or `command-result` used directly as the condition;
- pure Bool condition that is still not lowerable by the minimal condition subset;
- variant-specific field use that would require proof but is attempted through `if` instead of `match`.

- [ ] **Step 3: Add failing tests before implementation**

Add or extend tests with these concrete names:

```python
test_elaborate_expression_supports_if_conditional
test_elaborate_expression_rejects_if_wrong_arity
test_typecheck_if_inherits_existing_proof_scope
test_typecheck_if_does_not_create_variant_proof
test_compile_stage3_normalizes_helper_calls_inside_if
test_function_dependency_walker_descends_through_if_expr
test_lowering_if_bool_literal_emits_shared_if_step
test_lowering_if_bool_ref_emits_artifact_bool_predicate
test_lowering_if_projects_branch_outputs_for_record_result
test_loop_recur_supports_if_routing_between_continue_and_done
test_rendered_diagnostic_reports_if_condition_not_bool
```

Use fixture-backed tests for compile/lowering cases and inline-expression tests for AST/typecheck cases. Keep assertions behavioral: AST node shape, diagnostic code, lowered shared `if` mapping shape, branch output refs, and loop projection behavior.

- [ ] **Step 4: Run collection for every new or renamed test module**

Run:

```bash
python -m pytest --collect-only \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_variant_proofs.py \
  tests/test_workflow_lisp_functions.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_diagnostics.py \
  tests/test_workflow_lisp_loop_recur.py -q
```

Expected:

- collection succeeds;
- the new `if` tests appear;
- any failures are implementation failures, not import/collection failures.

## Task 2: Add `IfExpr` Elaboration And The Minimal Condition Classifier

**Files:**

- Create: `orchestrator/workflow_lisp/conditionals.py`
- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/__init__.py`

- [ ] **Step 1: Extend the expression AST and exports**

Add `IfExpr` to the expression dataclasses, `ExprNode`, and `__all__` exports. Keep span/form-path ownership on the authored `if` form.

- [ ] **Step 2: Teach `_elaborate_list(...)` to recognize authored `if`**

In `expressions.py`:

- detect `head.resolved_name == "if"`;
- require exactly three child expressions after the head;
- raise `if_form_invalid` on malformed arity or non-list misuse;
- elaborate the condition, then branch, and else branch with the current `bound_names`.

Do not add parser changes in `reader.py` or `syntax.py`; this is just one new special form in expression elaboration.

- [ ] **Step 3: Add `conditionals.py` with the narrow projectability model**

Implement the classifier so only these authored shapes pass:

- `LiteralExpr(..., literal_kind="bool")`
- `NameExpr` whose already-typed result is `Bool`
- `FieldAccessExpr` whose already-typed result is `Bool`

Reject everything else with `if_condition_not_projectable`, including:

- nested `let*` as the condition;
- pure helper expansions that normalize into unsupported composite shapes;
- comparisons or future predicate forms that are not part of this slice.

- [ ] **Step 4: Run the expression-focused tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_expressions.py -q
```

Expected:

- elaboration tests pass for valid ternary `if`;
- malformed arity fails with `if_form_invalid`.

## Task 3: Extend Typechecking, Proof Rules, And Helper Traversals

**Files:**

- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/functions.py`
- Modify: `tests/test_workflow_lisp_variant_proofs.py`
- Modify: `tests/test_workflow_lisp_functions.py`

- [ ] **Step 1: Add the authored `if` case in `_typecheck(...)`**

Typecheck in this order:

1. typecheck `condition_expr`;
2. require `PrimitiveTypeRef(name="Bool")`;
3. require `typed_condition.effect_summary == EMPTY_EFFECT_SUMMARY`;
4. call the new condition classifier to prove the condition can lower honestly;
5. typecheck `then_expr` and `else_expr` under the inherited `value_env` and unchanged `proof_scope`;
6. unify branch result types.

For branch type convergence:

- use exact equality for ordinary types;
- reuse `_unify_loop_control_types(...)` so loop-body `if` can combine `continue` and `done` paths the same way `match` already does.

- [ ] **Step 2: Preserve proof rules exactly**

Ensure:

- both branches inherit the current `ProofScope` unchanged;
- `if` never adds `ProofFact`;
- conditions that attempt to use variant-only fields without existing proof continue to fail with `variant_ref_unproved` or `variant_ref_wrong_variant`.

- [ ] **Step 3: Extend helper normalization and purity traversal**

Update `functions.py` so every existing helper utility descends through `IfExpr`:

- `_normalize_expr(...)`
- `_clone_function_expr(...)`
- `_function_dependencies(...)`
- `_find_purity_violation(...)`

This is required so `defun` normalization can rewrite helper calls that appear in conditions or branches and so purity/dependency analysis does not silently skip those nodes.

- [ ] **Step 4: Run proof and helper tests**

Run:

```bash
python -m pytest \
  tests/test_workflow_lisp_variant_proofs.py \
  tests/test_workflow_lisp_functions.py -q
```

Expected:

- inherited proof works inside both branches of an enclosing `match`;
- `if` does not create proof by itself;
- helper normalization and dependency walking both traverse `IfExpr`.

## Task 4: Lower Authored `if` Through Shared Branching And Extend Loop-Body Lowering

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_loop_recur.py`

- [ ] **Step 1: Add a dedicated `_lower_if_expr(...)` path**

In `lowering.py`:

- add an `IfExpr` branch in `_lower_expression(...)`;
- lower the condition through the new classifier and predicate renderer;
- emit one shared authored `if` step with `if_condition`, `then_branch`, and `else_branch`;
- return `_TerminalResult(..., output_kind="if")` with ordinary `output_refs`.

- [ ] **Step 2: Reuse existing branch-output projection instead of inventing a new transport**

Generalize the projection logic currently embedded in `_lower_match_expr(...)` so `if` and `match` can both:

- lower branch-local child steps;
- build per-branch `outputs` mappings from typed return contracts;
- insert a projection-anchor step when a branch has no emitted child steps but still needs stable output refs;
- preserve origin mapping for the conditional step, branch block ids, and projection-anchor steps.

Support the same result categories already exercised elsewhere:

- `PrimitiveTypeRef`
- `PathTypeRef`
- `RecordTypeRef`
- `UnionTypeRef`

Keep `workflow_return_not_exportable` for types that still cannot cross the existing projection surface.

- [ ] **Step 3: Keep Bool guard rendering honest and shared**

Refactor `_render_boolean_predicate(...)` or delegate it to `conditionals.py` so authored `if` and existing Bool guard paths use one predicate encoder. Preserve current literal/`ref` behavior for existing callers; do not broaden the predicate language.

- [ ] **Step 4: Extend lowering-time expression helpers for `IfExpr`**

Update the existing lowering-time helpers so authored conditionals work in `let*` and loops:

- `_resolve_inline_expr_value(...)`
- `_binding_type_for_expr(...)` if `IfExpr` can become an effectful binding source
- `_resolve_lowering_expr_type(...)`
- any branch-local type-binding or projection helper needed to infer `IfExpr` result types

The goal is that a `let*` binding whose value is an `if` expression can feed later lowering exactly as a `match` or `loop/recur` result does today.

- [ ] **Step 5: Extend `_lower_loop_body_expr(...)` for authored `if`**

Permit `IfExpr` inside loop bodies only by routing to the existing loop-frame contract:

- both branches must lower to the current loop output projection shape;
- `continue` and `done` remain the only terminal loop-control forms;
- no loop exhaustion, accumulator, or cross-iteration proof behavior changes.

- [ ] **Step 6: Run lowering and loop regression tests**

Run:

```bash
python -m pytest \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_loop_recur.py -q
```

Expected:

- lowered workflows contain a shared `if` step rather than ad hoc glue;
- Bool-ref conditions use `artifact_bool` or the existing shared Bool predicate surface;
- branch outputs project through stable refs;
- loop-body `if` composes with `continue`/`done`.

## Task 5: Diagnostics, Narrow Regression, And Completion Evidence

**Files:**

- Modify: `tests/test_workflow_lisp_diagnostics.py`
- Reuse all touched implementation/test files above

- [ ] **Step 1: Add diagnostic rendering coverage for the new codes**

Add tests that compile invalid fixtures and assert rendered/serialized diagnostics include:

- the expected `if_*` code;
- the authored file/line/form path;
- no fallback or generic runtime-only error where a frontend diagnostic should exist.

- [ ] **Step 2: Run the full narrow regression set for this slice**

Run:

```bash
python -m pytest \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_variant_proofs.py \
  tests/test_workflow_lisp_functions.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_diagnostics.py \
  tests/test_workflow_lisp_loop_recur.py -q
```

Expected:

- all conditional-slice tests pass together;
- there are no regressions in proof reset, helper normalization, or loop lowering caused by the new node.

- [ ] **Step 3: Record completion evidence in the work log or handoff**

When implementation is done, capture:

- which files changed;
- which fixtures and tests were added;
- the exact `pytest` commands run and whether they passed;
- any residual risk, especially if branch-output projection had to be generalized more broadly than planned.

## Acceptance Checklist

- [ ] Authored Workflow Lisp accepts `(if condition then-expr else-expr)`.
- [ ] Conditions must be pure and exact-`Bool`.
- [ ] Only Bool literals and already-legal Bool refs/field refs lower successfully.
- [ ] `if` inherits proof scope and creates no new proof facts.
- [ ] Branch effects are preserved in the typed effect summary.
- [ ] Lowered conditionals use shared authored/core `if` lineage, not hidden helpers.
- [ ] Conditional results flow through `let*`, ordinary returns, and `loop/recur`.
- [ ] No new command adapter, report parser, pointer-as-authority rule, or runtime-native branching surface is introduced.
