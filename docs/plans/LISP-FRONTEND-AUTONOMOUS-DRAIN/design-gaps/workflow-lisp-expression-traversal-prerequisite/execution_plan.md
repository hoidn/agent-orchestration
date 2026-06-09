# Workflow Lisp Expression Traversal Prerequisite Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` to execute this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the bounded expression-traversal prerequisite by adding one shared structural traversal owner for Workflow Lisp expressions, migrating only the first low-risk adopter set to that owner, and proving every current `ExprNode` member is either traversed through that helper or explicitly classified as a leaf.

**Architecture:** Keep the change inside the frontend-owned `orchestrator/workflow_lisp/` package. Add a new narrow `expression_traversal.py` owner that depends only on expression-model dataclasses and helper spec dataclasses, exposes `iter_child_exprs(expr)` plus pre-order `walk_expr(expr)`, and does not take ownership of environments, proof facts, local values, lowering context, or same-file procedure recursion. Then migrate only the selected mechanical adopters: helper dependency scanning in `functions.py`, procedure-call dependency scanning in `compiler.py`, workflow extern collection in `workflow_refs.py`, ProcRef specialization discovery in `procedure_specialization.py`, and same-file workflow extern discovery in `lowering/phase_scope.py`.

**Tech Stack:** Python 3, dataclasses, the existing Workflow Lisp frontend pipeline in `orchestrator/workflow_lisp`, shared workflow validation/runtime surfaces in `orchestrator.workflow`, pytest, `ast`/source inspection for owner-boundary regressions, and the focused verification selectors recorded in the selected implementation architecture.

---

## Fixed Inputs

Treat these as authority for this slice:

- `docs/index.md`
- `docs/steering.md`
  - currently empty in this checkout; it does not widen scope
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - especially sections `8.1`, `9.7`, `9.7.1`, and `24`
- `docs/design/workflow_lisp_refactor_architecture.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/2026-06-02-workflow-lisp-low-hanging-refactor-plan.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-expression-traversal-prerequisite/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/6/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`
  - currently `{"ledger_version":1,"events":[]}`; no later ledger event supersedes this prerequisite

Read these implementation seams before editing:

- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/functions.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/workflow_refs.py`
- `orchestrator/workflow_lisp/procedure_specialization.py`
- `orchestrator/workflow_lisp/lowering/phase_scope.py`
- `orchestrator/workflow_lisp/resource_stdlib.py`
- `orchestrator/workflow_lisp/drain_stdlib.py`
- `orchestrator/workflow_lisp/phase_stdlib.py`
- `tests/test_workflow_lisp_expressions.py`
- `tests/test_workflow_lisp_functions.py`
- `tests/test_workflow_lisp_workflow_refs.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_lowering.py`

## Current Checkout Starting Point

Implementation must start from the code that exists now:

- `orchestrator/workflow_lisp/expression_traversal.py` does not exist.
- The current public `ExprNode` union in `orchestrator/workflow_lisp/expressions.py` contains exactly these members:
  - `NameExpr`
  - `LiteralExpr`
  - `FieldAccessExpr`
  - `RecordExpr`
  - `UnionVariantExpr`
  - `LetStarExpr`
  - `IfExpr`
  - `MatchExpr`
  - `CallExpr`
  - `FunctionCallExpr`
  - `ProcedureCallExpr`
  - `WithPhaseExpr`
  - `PhaseTargetExpr`
  - `GeneratedRelpathSeedExpr`
  - `WorkflowRefLiteralExpr`
  - `ProcRefLiteralExpr`
  - `BindProcExpr`
  - `LetProcExpr`
  - `ProviderResultExpr`
  - `CommandResultExpr`
  - `ContinueExpr`
  - `DoneExpr`
  - `LoopRecurExpr`
  - `RunProviderPhaseExpr`
  - `ProduceOneOfExpr`
  - `StdlibSpecializationExpr`
  - `ResumeOrStartExpr`
  - `ResourceTransitionExpr`
  - `FinalizeSelectedItemExpr`
  - `BacklogDrainExpr`
- `LoopBodyFnExpr` exists in `expressions.py` but is not part of the `ExprNode` union. It remains compiler-owned and is out of scope for the public traversal contract in this slice.
- `functions.py::_function_dependencies(...)` still hardcodes recursion for a small subset of expression forms.
- `compiler.py::_procedure_dependencies(...)` still carries an inline walker that misses much of the current `ExprNode` union.
- `workflow_refs.py::collect_workflow_extern_names(...)` still hardcodes structural descent plus provider/prompt collection in one recursion tree.
- `procedure_specialization.py::discover_proc_ref_specializations(...)` still duplicates most structural recursion while also threading a ProcRef environment.
- `lowering/phase_scope.py::_workflow_extern_requirements(...)` still hardcodes provider/prompt descent plus same-file procedure recursion in one walker.
- `tests/test_workflow_lisp_expressions.py` currently guards older surface removals such as `ReviewReviseLoopExpr`, but it does not yet prove shared traversal coverage for the current `ExprNode` union.

Current file sizes for the affected code paths:

- `orchestrator/workflow_lisp/functions.py`: 871 lines
- `orchestrator/workflow_lisp/compiler.py`: 3,175 lines
- `orchestrator/workflow_lisp/workflow_refs.py`: 378 lines
- `orchestrator/workflow_lisp/procedure_specialization.py`: 1,128 lines
- `orchestrator/workflow_lisp/lowering/phase_scope.py`: 1,808 lines

## Scope Limits

In scope:

- add exactly one shared owner module at `orchestrator/workflow_lisp/expression_traversal.py`
- define the direct-child traversal contract for the current `ExprNode` union
- add pre-order `walk_expr(...)` on top of that direct-child contract
- migrate only the first low-risk adopter set named in the implementation architecture
- add coverage-style tests that fail closed when a new `ExprNode` member is added without updating the shared helper
- add only the narrow behavior regressions needed to prove the helper preserves provider/prompt discovery, ProcRef specialization discovery, and dependency scanning for the selected adopters

Out of scope:

- a generic visitor framework, callback registry, rewrite engine, or second expression IR
- Track A form-registry work, imported `.orc` expansion, or review-loop bridge retirement
- new Workflow Lisp syntax, type-system behavior, lowering semantics, or runtime behavior
- typecheck-family or lowering-family decomposition beyond consuming the helper in the named adopters
- moving every duplicated walker in the repo to the new helper
- new scripts, command adapters, runtime-native effects, backlog updates, queue edits, or progress-ledger edits

## Locked Decisions

Do not re-decide these during implementation.

Traversal API contract:

- Create `orchestrator/workflow_lisp/expression_traversal.py` as the only shared owner for direct child-expression enumeration.
- Export exactly:
  - `iter_child_exprs(expr: ExprNode) -> tuple[ExprNode, ...]`
  - `walk_expr(expr: ExprNode) -> Iterator[ExprNode]`
- `iter_child_exprs(...)` returns direct children only, in stable authored order.
- `walk_expr(...)` is deterministic pre-order: current node first, then descendants in the order provided by `iter_child_exprs(...)`.
- The helper stays structural only. It must not carry environments, proof facts, local values, same-file procedure recursion, or lowering context.

Coverage contract:

- Add one explicit leaf-classification test and one explicit direct-child coverage test for the current `ExprNode` union.
- Compare the helper's explicit classification against `set(get_args(ExprNode))` so future expression additions fail loudly until the helper is updated.
- `LoopBodyFnExpr` is not part of this proof because it is not in the `ExprNode` union.

Leaf classification:

- Keep these as childless leaves:
  - `NameExpr`
  - `LiteralExpr`
  - `FieldAccessExpr`
  - `PhaseTargetExpr`
  - `GeneratedRelpathSeedExpr`
  - `WorkflowRefLiteralExpr`
  - `ProcRefLiteralExpr`

Direct-child contract:

- `iter_child_exprs(...)` must expose children for:
  - `RecordExpr` via field values
  - `UnionVariantExpr` via field values
  - `LetStarExpr` via binding values then body
  - `IfExpr` via condition, then, else
  - `MatchExpr` via subject then arm bodies
  - `CallExpr` via binding values
  - `FunctionCallExpr` via args
  - `ProcedureCallExpr` via args
  - `WithPhaseExpr` via `ctx_expr` then `body`
  - `BindProcExpr` via `base_expr` then binding value expressions
  - `LetProcExpr` via `binding.local_body` then `body`
  - `ProviderResultExpr` via provider, prompt, then inputs
  - `CommandResultExpr` via argv values
  - `ContinueExpr` via `state_expr`
  - `DoneExpr` via `result_expr`
  - `LoopRecurExpr` via max-iterations, initial-state, body, then optional `on_exhausted_result_expr`
  - `RunProviderPhaseExpr` via `ctx_expr`, `inputs_expr`, provider, prompt
  - `ProduceOneOfExpr` via `ctx_expr`, optional producer provider/prompt expressions, producer inputs, then non-`None` candidate `target_expr` values
  - `StdlibSpecializationExpr` via `expr_operands` values
  - `ResumeOrStartExpr` via `ctx_expr`, `resume_from_expr`, `start_expr`
  - `ResourceTransitionExpr` via `spec.ctx_expr`, optional `spec.when_expr`, `spec.resource_expr`, `spec.ledger_expr`
  - `FinalizeSelectedItemExpr` via `spec.ctx_expr`, `spec.selected_expr`, `spec.queue_transition_expr`, `spec.roadmap_expr`, `spec.plan_expr`, `spec.implementation_expr`
  - `BacklogDrainExpr` via `spec.ctx_expr`, optional `spec.providers_expr`, `spec.max_iterations_expr`
- Do not traverse compile-derived helper state such as `ResumeOrStartExpr.validation_spec`; this slice is about authored/frontend expression structure only.

Adopter contract:

- `functions.py::_function_dependencies(...)` must switch to `walk_expr(...)` and collect `FunctionCallExpr.callee_name`.
- `compiler.py::_procedure_dependencies(...)` must switch to `walk_expr(...)` and collect `ProcedureCallExpr.callee_name`.
- `workflow_refs.py::collect_workflow_extern_names(...)` must keep node-specific provider/prompt collection for `ProviderResultExpr`, `RunProviderPhaseExpr`, and `ProduceOneOfExpr`, but delegate generic structural descent to `iter_child_exprs(...)`.
- `procedure_specialization.py::discover_proc_ref_specializations(...)` must keep explicit handling for:
  - `ProcedureCallExpr`
  - `LetStarExpr`
  - binding-time ProcRef environment extension
  but delegate ordinary structural descent for the remaining node kinds to `iter_child_exprs(...)`.
- `lowering/phase_scope.py::_workflow_extern_requirements(...)` must keep explicit handling for:
  - `ProviderResultExpr`
  - `RunProviderPhaseExpr`
  - `ProduceOneOfExpr`
  - same-file `ProcedureCallExpr` recursion into typed procedure bodies
  but delegate ordinary structural descent to `iter_child_exprs(...)`.

Boundary contract:

- The new helper module may import expression dataclasses and helper spec dataclasses from:
  - `expressions.py`
  - `phase_stdlib.py`
  - `resource_stdlib.py`
  - `drain_stdlib.py`
- It must not import:
  - `compiler.py`
  - `workflow_refs.py`
  - `procedure_specialization.py`
  - `typecheck*.py`
  - `lowering/*`
  - shared runtime or shared validation packages
- Do not widen the package-root public API in `orchestrator/workflow_lisp/__init__.py` for this slice.

## File Ownership

Create:

- `orchestrator/workflow_lisp/expression_traversal.py`

Modify:

- `orchestrator/workflow_lisp/functions.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/workflow_refs.py`
- `orchestrator/workflow_lisp/procedure_specialization.py`
- `orchestrator/workflow_lisp/lowering/phase_scope.py`
- `tests/test_workflow_lisp_expressions.py`
- `tests/test_workflow_lisp_functions.py`
- `tests/test_workflow_lisp_workflow_refs.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_lowering.py`

Reuse without broadening ownership:

- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/phase_stdlib.py`
- `orchestrator/workflow_lisp/resource_stdlib.py`
- `orchestrator/workflow_lisp/drain_stdlib.py`
- shared validation/runtime modules under `orchestrator/workflow/`

## Acceptance Target

This prerequisite is complete only when all of the following are true:

- `orchestrator/workflow_lisp/expression_traversal.py` exists and is the only shared owner for direct child-expression enumeration
- every current `ExprNode` union member is either traversed by `iter_child_exprs(...)` or explicitly classified as a leaf in tests
- `walk_expr(...)` yields deterministic pre-order traversal
- the selected adopters consume the shared helper instead of maintaining separate structural recursion trees
- provider/prompt extern discovery still sees nested command/provider-bearing forms rather than treating them as opaque leaves
- ProcRef specialization discovery still preserves its binding environment semantics while delegating generic structural descent
- the exact focused verification commands below pass

## Task 1: Lock The Traversal Contract And Architecture Regressions First

**Files:**

- Modify: `tests/test_workflow_lisp_expressions.py`
- Modify: `tests/test_workflow_lisp_functions.py`
- Modify: `tests/test_workflow_lisp_workflow_refs.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_lowering.py`

- [ ] **Step 1: Add the helper-surface contract tests**

In `tests/test_workflow_lisp_expressions.py`, add focused tests that define the contract before code changes:

- one test that imports `orchestrator.workflow_lisp.expression_traversal` and asserts `iter_child_exprs` plus `walk_expr` are present and callable
- one test that compares `set(get_args(ExprNode))` against two explicit sets:
  - leaf-only expression classes
  - expression classes that must produce children through `iter_child_exprs(...)`
- one representative direct-child-order test for the non-trivial carriers most likely to regress:
  - `LetProcExpr`
  - `LoopRecurExpr` with `on_exhausted_result_expr`
  - `ProduceOneOfExpr`
  - `ResourceTransitionExpr`
  - `FinalizeSelectedItemExpr`
  - `BacklogDrainExpr`
- one representative pre-order traversal test for a nested composite expression that combines:
  - `WithPhaseExpr`
  - `MatchExpr`
  - `FunctionCallExpr` or `ProcedureCallExpr`
  - `ContinueExpr` or `DoneExpr`

Expected before implementation: importing `orchestrator.workflow_lisp.expression_traversal` fails because the module does not exist.

- [ ] **Step 2: Add owner-boundary tests for the adopter modules**

Add narrow source-structure guards that will fail until the adopters use the shared helper:

- in `tests/test_workflow_lisp_functions.py`
  - assert `functions.py` references `walk_expr`
- in `tests/test_workflow_lisp_procedures.py`
  - assert `procedure_specialization.py` references `iter_child_exprs`
- in `tests/test_workflow_lisp_workflow_refs.py`
  - assert `workflow_refs.py` references `iter_child_exprs`
- in `tests/test_workflow_lisp_lowering.py`
  - assert `lowering/phase_scope.py` references `iter_child_exprs`
- add one compiler-focused regression in either `tests/test_workflow_lisp_procedures.py` or `tests/test_workflow_lisp_expressions.py`
  - assert `compiler.py` references `walk_expr` inside `_procedure_dependencies(...)`

Use the same `ast`/source-inspection style already present elsewhere in the Workflow Lisp tests. Do not snapshot whole files; assert only the new owner-boundary facts.

- [ ] **Step 3: Add one concrete behavioral regression per structural adopter family**

Add narrow behavior tests that prove the shared helper is not only imported, but materially fixes current recursion gaps:

- compiler dependency scanning:
  - direct-call `_procedure_dependencies(...)` on a nested expression tree that hides a `ProcedureCallExpr` under at least one currently missed container such as `LoopRecurExpr`, `WithPhaseExpr`, `BindProcExpr`, `LetProcExpr`, or `StdlibSpecializationExpr`
- workflow extern collection:
  - direct-call `collect_workflow_extern_names(...)` on a nested tree that requires structural descent through at least one currently missed container, such as `WithPhaseExpr`, `BindProcExpr`, `LetProcExpr`, `StdlibSpecializationExpr`, or `ProduceOneOfExpr` candidate `target_expr`
- lowering phase-scope extern collection:
  - compile or construct a same-file workflow/procedure case where provider/prompt discovery requires both:
    - ordinary structural descent through a currently missed container
    - same-file procedure recursion that must remain explicit

Keep these tests narrow. They are proving structural traversal reuse, not redesigning these analyzers.

- [ ] **Step 4: Collect the touched tests before implementation**

Run:

```bash
pytest --collect-only \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_functions.py \
  tests/test_workflow_lisp_workflow_refs.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_lowering.py \
  -q
```

Expected: the new tests collect successfully.

- [ ] **Step 5: Run the narrow failing regressions**

Run only the new contract and owner-boundary tests first.

Expected before code changes:

- the helper-module import test fails because `expression_traversal.py` is missing
- the owner-boundary source guards fail because the adopters do not yet reference `iter_child_exprs` / `walk_expr`
- the behavioral regressions fail where current manual walkers miss the nested containers selected in Step 3

- [ ] **Step 6: Commit**

```bash
git add \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_functions.py \
  tests/test_workflow_lisp_workflow_refs.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_lowering.py
git commit -m "test: lock workflow lisp traversal prerequisite regressions"
```

## Task 2: Add The Shared Traversal Owner And Prove Full `ExprNode` Coverage

**Files:**

- Create: `orchestrator/workflow_lisp/expression_traversal.py`
- Modify: `tests/test_workflow_lisp_expressions.py`

- [ ] **Step 1: Create `expression_traversal.py` with the locked public surface**

Add `orchestrator/workflow_lisp/expression_traversal.py` and implement:

- `iter_child_exprs(expr: ExprNode) -> tuple[ExprNode, ...]`
- `walk_expr(expr: ExprNode) -> Iterator[ExprNode]`

Implementation constraints:

- depend only on frontend expression-model classes and the helper spec dataclasses named in the architecture
- preserve stable authored order
- use one obvious branch per `ExprNode` family rather than a dynamic reflection scheme
- treat the compile-derived helper specs as containers only for their authored child expressions
- keep unknown coverage failures out of runtime logic; the fail-closed coverage proof lives in tests

- [ ] **Step 2: Implement the full direct-child classification**

Handle every current `ExprNode` member exactly once.

Be explicit about these cases:

- `FieldAccessExpr` stays a leaf even though it contains a `NameExpr` base field; do not recurse into the base because the expression model treats field access as one atomic value reference rooted at a lexical name
- `ResumeOrStartExpr.validation_spec` is not part of the authored child-expression contract for this helper
- `ProduceOneOfExpr` must traverse producer expressions and candidate `target_expr` values, but not invent children from metadata-only strings
- `StdlibSpecializationExpr` must traverse only `expr_operands` values, not the symbolic operands

- [ ] **Step 3: Implement deterministic pre-order `walk_expr(...)`**

`walk_expr(...)` must:

- yield the current node first
- then yield descendants by recursively iterating over `iter_child_exprs(...)`
- avoid special scoping behavior; specialized walkers will layer their own semantics on top

- [ ] **Step 4: Re-run only the expression helper tests**

Run the new `tests/test_workflow_lisp_expressions.py` selectors first.

Expected: the helper-surface import, coverage-classification tests, direct-child-order tests, and pre-order traversal tests now pass.

- [ ] **Step 5: Commit**

```bash
git add \
  orchestrator/workflow_lisp/expression_traversal.py \
  tests/test_workflow_lisp_expressions.py
git commit -m "feat: add workflow lisp expression traversal helpers"
```

## Task 3: Migrate The Purely Structural Adopters To `walk_expr(...)`

**Files:**

- Modify: `orchestrator/workflow_lisp/functions.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `tests/test_workflow_lisp_functions.py`
- Modify: `tests/test_workflow_lisp_procedures.py`

- [ ] **Step 1: Switch `_function_dependencies(...)` to `walk_expr(...)`**

In `functions.py`:

- import `walk_expr` from `expression_traversal.py`
- replace the handwritten recursion tree in `_function_dependencies(...)`
- collect `callee_name` for each `FunctionCallExpr` seen during traversal

Do not redesign purity validation in this slice. `_find_purity_violation(...)` remains its own explicit semantic walker.

- [ ] **Step 2: Switch `_procedure_dependencies(...)` to `walk_expr(...)`**

In `compiler.py`:

- import `walk_expr` locally or at module scope, consistent with existing import patterns
- replace the nested `walk(...)` recursion inside `_procedure_dependencies(...)`
- collect `callee_name` for each `ProcedureCallExpr` seen during traversal

Do not move ownership of dependency scanning out of `compiler.py` in this slice; only replace duplicated structural recursion.

- [ ] **Step 3: Re-run the functions/compiler regressions**

Run the source-guard tests and the narrow behavior regressions for:

- helper dependency scanning
- procedure dependency scanning

Expected: the new source guards pass and the selected nested dependency cases now resolve correctly.

- [ ] **Step 4: Commit**

```bash
git add \
  orchestrator/workflow_lisp/functions.py \
  orchestrator/workflow_lisp/compiler.py \
  tests/test_workflow_lisp_functions.py \
  tests/test_workflow_lisp_procedures.py
git commit -m "refactor: reuse shared traversal for dependency scans"
```

## Task 4: Migrate The Scoped Adopters While Keeping Their Local Semantics Explicit

**Files:**

- Modify: `orchestrator/workflow_lisp/workflow_refs.py`
- Modify: `orchestrator/workflow_lisp/procedure_specialization.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_scope.py`
- Modify: `tests/test_workflow_lisp_workflow_refs.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_lowering.py`

- [ ] **Step 1: Update `collect_workflow_extern_names(...)` to delegate structural descent**

In `workflow_refs.py`:

- keep explicit provider/prompt extraction for:
  - `ProviderResultExpr`
  - `RunProviderPhaseExpr`
  - `ProduceOneOfExpr`
- after that explicit logic, recurse through `iter_child_exprs(...)` instead of hand-maintaining separate branches for ordinary containers

Do not change the extern rebinding contract or the returned tuple shape.

- [ ] **Step 2: Update `discover_proc_ref_specializations(...)` to delegate non-scoped descent**

In `procedure_specialization.py`:

- keep explicit handling for:
  - `ProcedureCallExpr`
  - `LetStarExpr`
  - ProcRef environment extension after binding evaluation
- for all remaining node kinds, recurse via `iter_child_exprs(...)`

Preserve the existing order of:

- walking bound expressions before extending the env
- resolving ProcRef literals against the current env
- recording newly discovered specializations only after the existing specialization checks run

- [ ] **Step 3: Update `_workflow_extern_requirements(...)` in `lowering/phase_scope.py`**

In `lowering/phase_scope.py`:

- keep explicit provider/prompt extraction for:
  - `ProviderResultExpr`
  - `RunProviderPhaseExpr`
  - `ProduceOneOfExpr`
- keep explicit same-file procedure recursion for `ProcedureCallExpr`
- delegate ordinary structural descent to `iter_child_exprs(...)` for the remaining containers

Do not collapse same-file procedure recursion into the shared helper; that behavior remains lowering-owned.

- [ ] **Step 4: Re-run the scoped adopter regressions**

Run the source-guard and narrow behavior regressions for:

- workflow extern collection
- ProcRef specialization discovery
- lowering phase-scope extern requirements

Expected: provider/prompt names remain visible through nested high-level forms, ProcRef specialization discovery still finds compile-time specializations, and same-file phase-scope extern discovery still descends into typed procedure bodies when required.

- [ ] **Step 5: Commit**

```bash
git add \
  orchestrator/workflow_lisp/workflow_refs.py \
  orchestrator/workflow_lisp/procedure_specialization.py \
  orchestrator/workflow_lisp/lowering/phase_scope.py \
  tests/test_workflow_lisp_workflow_refs.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_lowering.py
git commit -m "refactor: share workflow lisp structural expression traversal"
```

## Task 5: Run The Required Verification Slice

**Files:**

- No new files; verify the touched implementation and tests

- [ ] **Step 1: Re-run touched test collection if any test names moved**

If any test names or modules changed during implementation, rerun:

```bash
pytest --collect-only \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_functions.py \
  tests/test_workflow_lisp_workflow_refs.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_lowering.py \
  -q
```

- [ ] **Step 2: Run the exact focused verification commands from the implementation architecture**

Run, in this order:

```bash
pytest tests/test_workflow_lisp_expressions.py -q
pytest tests/test_workflow_lisp_functions.py -q
pytest tests/test_workflow_lisp_workflow_refs.py -q
pytest tests/test_workflow_lisp_procedures.py -q
pytest tests/test_workflow_lisp_lowering.py -q
python -m compileall orchestrator/workflow_lisp
git diff --check
```

Expected: all five focused selectors pass, compileall succeeds, and `git diff --check` is clean.

- [ ] **Step 3: Record any widened verification only if the narrow slice demands it**

If a failure shows a touched adopter shares helper code with a broader selector, record:

- the first failing narrow command and its exact output
- the reason a wider selector is necessary
- the wider selector run and result

Do not widen verification preemptively.

- [ ] **Step 4: Commit the final traversal prerequisite**

```bash
git add \
  orchestrator/workflow_lisp/expression_traversal.py \
  orchestrator/workflow_lisp/functions.py \
  orchestrator/workflow_lisp/compiler.py \
  orchestrator/workflow_lisp/workflow_refs.py \
  orchestrator/workflow_lisp/procedure_specialization.py \
  orchestrator/workflow_lisp/lowering/phase_scope.py \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_functions.py \
  tests/test_workflow_lisp_workflow_refs.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_lowering.py
git commit -m "refactor: add workflow lisp traversal owner surface"
```
