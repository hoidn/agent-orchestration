# Workflow Lisp Low-Hanging Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce maintenance cost in `orchestrator/workflow_lisp` through behavior-preserving, low-risk refactors.

**Architecture:** Follow
[Workflow Lisp Refactor Architecture](../design/workflow_lisp_refactor_architecture.md).
Keep the existing pass-oriented compiler architecture. First fix concrete
low-risk hazards found by the module review, then add characterization coverage,
then decide whether `lowering.py` should become a `lowering/` package before
extracting read-only helpers and coherent lowering helper clusters. Preserve the
`orchestrator.workflow_lisp.lowering` import facade and do not change `.orc`
syntax, generated workflow behavior, diagnostics, source maps, or runtime
contracts.

**Tech Stack:** Python, pytest, Workflow Lisp frontend, existing orchestrator workflow loader/runtime.

---

## Context

This plan is a narrow execution companion to
`docs/plans/2026-05-23-workflow-lisp-refactoring-backlog.md` and the design in
[Workflow Lisp Refactor Architecture](../design/workflow_lisp_refactor_architecture.md).

The current compiler shape is sound enough to preserve:

- reader and S-expression parsing;
- syntax objects with spans and expansion provenance;
- macro expansion;
- definition, function, procedure, and workflow elaboration;
- type/effect checking;
- lowering into ordinary workflow dictionaries;
- shared loader/runtime validation;
- source-map and build-artifact emission.

The low-hanging debt is accretive complexity:

- repeated expression-tree walkers;
- helper clusters embedded in `lowering.py`;
- no explicit package boundary for very large modules such as `lowering.py`;
- fixture-only code in the production package;
- an overly broad package-root public API.

## Findings From Module Review

A module-by-module review of `orchestrator/workflow_lisp` promoted several
items from general refactor debt to first-tranche work:

- `lowering.py` has concrete hazards in addition to size: duplicate helper
  definitions are silently shadowed, and a private-workflow type-analysis path
  references `VariantCaseTypeRef` without importing it.
- `functions.py` purity checking currently fails open for unknown expression
  nodes. New effectful expression forms could be accepted in `defun` until a
  later pass fails less clearly.
- `macros.py` hygiene handlers can index malformed macro output before
  downstream validators produce owned, source-mapped diagnostics.
- expression traversal is duplicated across `functions.py`, `compiler.py`,
  `workflow_refs.py`, `lowering.py`, and `typecheck.py`; this is the highest
  leverage refactor after the immediate hazards.
- lint and diagnostic metadata should be hardened before more rules are added:
  lint severities are unconstrained strings, and unknown diagnostic codes can
  silently default to parse/read metadata.
- focused loop/phase-stdlib verification reported current failures:
  `python -m pytest tests/test_workflow_lisp_loop_recur.py tests/test_workflow_lisp_phase_stdlib.py -q`
  returned `91 passed, 4 failed`. Treat these as known preconditions before
  relying on those selectors as clean refactor guards.

## Non-Goals

- Do not redesign the compiler pipeline.
- Do not change authored `.orc` syntax.
- Do not add new language features.
- Do not remove legacy phase bridge behavior in this tranche.
- Do not rewrite `lowering.py` wholesale.
- Do not weaken source maps, diagnostics, effect visibility, contract validation,
  or generated workflow parity.

## Files And Responsibilities

- `tests/test_workflow_lisp_*.py`: characterization coverage for behavior that
  must survive refactors.
- `orchestrator/workflow_lisp/expression_traversal.py`: shared, small expression
  traversal helpers.
- `orchestrator/workflow_lisp/lowering.py`: current lowering module. This plan
  must decide whether to keep it as a file for this tranche or convert it to a
  package facade.
- `orchestrator/workflow_lisp/lowering/__init__.py`: package facade if the
  package split is chosen. It must preserve existing imports from
  `orchestrator.workflow_lisp.lowering`.
- `orchestrator/workflow_lisp/lowering/externs.py`: provider/prompt extern
  discovery for lowered workflows if the package split is chosen.
- `orchestrator/workflow_lisp/lowering/types.py`: lowering-time type inference
  helpers if the package split is chosen.
- `orchestrator/workflow_lisp/lowering_externs.py`: interim sibling-module
  fallback only if the package split is explicitly deferred.
- `orchestrator/workflow_lisp/lowering_types.py`: interim sibling-module
  fallback only if the package split is explicitly deferred.
- `orchestrator/workflow_lisp/__init__.py`: stable public package facade.
- `tests/support/workflow_lisp/runtime_closure_design_fixtures.py`: fixture-only
  runtime-closure rejection harness, if moved.
- `orchestrator/workflow_lisp/README.md`: package ownership map.
- `docs/plans/2026-05-23-workflow-lisp-refactoring-backlog.md`: update status
  and boundaries after this tranche lands.

## Task 0: Fix Concrete Review Hazards

**Files:**
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `orchestrator/workflow_lisp/functions.py`
- Modify: `orchestrator/workflow_lisp/macros.py`
- Modify: focused tests near the touched behavior

- [ ] **Step 1: Remove shadowed lowering helpers**

Remove duplicate definitions for:

- `_origin_for_workflow`;
- `_procedure_provenance_notes`;
- `_definition_only_module`.

Keep the later effective implementation unless inspection shows the earlier
implementation contains required behavior. Add or run a lint/static check that
catches duplicate definitions where available.

- [ ] **Step 2: Fix missing private-workflow type import**

Import or otherwise resolve `VariantCaseTypeRef` in `lowering.py` where the
private-workflow type-analysis branch references it. Add the smallest focused
test that exercises a private workflow path with variant-case field access, if
an existing fixture does not already cover it.

- [ ] **Step 3: Make `defun` purity fail closed**

Update `_find_purity_violation` so unknown `ExprNode` containers cannot silently
count as pure. Prefer a diagnostic or explicit internal unsupported-expression
path over returning `None`.

- [ ] **Step 4: Guard macro hygiene shape assumptions**

Add shape guards for known hygiene handlers such as `match` and `defworkflow`.
Malformed macro output should preserve expansion provenance and reach the normal
elaboration/typecheck diagnostic path instead of raising an uncaught index
error.

- [ ] **Step 5: Run focused checks**

Run:

```bash
python -m compileall orchestrator/workflow_lisp
pytest \
  tests/test_workflow_lisp_functions.py \
  tests/test_workflow_lisp_macros.py \
  tests/test_workflow_lisp_lowering.py \
  -q
git diff --check
```

Expected: compile and diff checks pass; focused tests pass or any pre-existing
failures are recorded with exact output before continuing.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/workflow_lisp/lowering.py orchestrator/workflow_lisp/functions.py orchestrator/workflow_lisp/macros.py tests
git commit -m "fix: harden workflow lisp refactor hazards"
```

## Task 1: Add Refactor Characterization Checks

**Files:**
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_structured_results.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_resource_stdlib.py`
- Modify: `tests/test_workflow_lisp_drain_stdlib.py`

- [ ] **Step 1: Identify existing representative fixtures**

Use existing fixtures where possible. Prefer fixtures already used by the test
suite for:

- `provider-result`;
- `command-result`;
- `with-phase` and `phase-target`;
- `resume-or-start`;
- `resource-transition`;
- `finalize-selected-item`;
- `backlog-drain`.

- [ ] **Step 2: Add behavior assertions**

Add narrow assertions for generated behavior. Prefer semantic assertions such as:

- generated step names for important boundaries exist;
- output contract kind is `output_bundle` or `variant_output`;
- source-map origin exists for one generated step;
- certified adapter binding is required for semantic adapter-backed forms;
- workflow call targets remain present inside lowered loop/control-flow bodies.

Do not add full snapshot tests for entire lowered workflows.

- [ ] **Step 3: Run focused tests**

Run:

```bash
pytest \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_structured_results.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_resource_stdlib.py \
  tests/test_workflow_lisp_drain_stdlib.py \
  -q
```

Expected: all selected tests pass before refactoring begins.

- [ ] **Step 4: Commit**

```bash
git add tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_resource_stdlib.py tests/test_workflow_lisp_drain_stdlib.py
git commit -m "test: characterize workflow lisp refactor surfaces"
```

## Task 2: Decide And Establish Lowering Package Boundary

**Files:**
- Move or Modify: `orchestrator/workflow_lisp/lowering.py`
- Create if chosen: `orchestrator/workflow_lisp/lowering/__init__.py`
- Test: import and focused Workflow Lisp lowering tests

Python cannot have both `orchestrator/workflow_lisp/lowering.py` and an
`orchestrator/workflow_lisp/lowering/` package with the same import path. This
task makes the structure decision before helper extraction so later tasks do not
create sibling modules that immediately need to be moved again.

Default decision: convert `lowering.py` into a package if the pure move is
low-risk. Defer only if import inventory shows a concrete blocker.

- [ ] **Step 1: Inventory lowering imports**

Run:

```bash
rg -n "workflow_lisp\\.lowering|from \\.lowering|import \\.lowering|from orchestrator\\.workflow_lisp import .*lower" orchestrator tests
```

Record whether callers import only the module facade or reach for file-local
details that need compatibility exports.

- [ ] **Step 2: Choose package or sibling-module fallback**

Choose one:

1. **Preferred:** convert `lowering.py` to a package facade.
2. **Fallback:** keep `lowering.py` for this tranche and use sibling helper
   modules such as `lowering_externs.py` and `lowering_types.py`.

Use the fallback only if the package conversion causes import instability that
would distract from the low-hanging refactor.

- [ ] **Step 3A: If package is chosen, perform a pure move**

Run:

```bash
mkdir -p orchestrator/workflow_lisp/lowering
git mv orchestrator/workflow_lisp/lowering.py orchestrator/workflow_lisp/lowering/__init__.py
```

Do not extract helpers in this step. Preserve every existing public symbol from
`orchestrator.workflow_lisp.lowering`.

- [ ] **Step 3B: If fallback is chosen, document the deferral**

Add a short note to this plan's implementation log or the final commit message
explaining why the package split was deferred. Continue with sibling modules in
Tasks 4 and 5.

- [ ] **Step 4: Run import checks**

Run:

```bash
python -m compileall orchestrator/workflow_lisp
pytest tests/test_workflow_lisp_lowering.py -q
```

Expected: imports and lowering tests pass with no behavior changes.

- [ ] **Step 5: Commit**

If package split was chosen:

```bash
git add orchestrator/workflow_lisp/lowering
git commit -m "refactor: make workflow lisp lowering a package facade"
```

If fallback was chosen:

```bash
git add docs/plans/2026-06-02-workflow-lisp-low-hanging-refactor-plan.md
git commit -m "docs: defer workflow lisp lowering package split"
```

## Task 3: Introduce Shared Expression Traversal Utility

**Files:**
- Create: `orchestrator/workflow_lisp/expression_traversal.py`
- Modify: `orchestrator/workflow_lisp/functions.py`
- Modify: `orchestrator/workflow_lisp/lowering/__init__.py` if package split
  was chosen
- Modify: `orchestrator/workflow_lisp/lowering.py` if package split was deferred
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Test: `tests/test_workflow_lisp_expressions.py` or nearest existing test file

- [ ] **Step 1: Write traversal tests**

Add tests for a small public helper such as:

```python
from orchestrator.workflow_lisp.expression_traversal import iter_child_exprs
```

Cover common expression shapes:

- `LetStarExpr`;
- `MatchExpr`;
- `IfExpr`;
- `RecordExpr`;
- `ProviderResultExpr`;
- `CommandResultExpr`;
- `ProduceOneOfExpr`;
- `ResumeOrStartExpr`;
- `ResourceTransitionExpr`;
- `BacklogDrainExpr`;
- leaf expressions.

Expected behavior: the helper returns only direct child expressions in stable
authoring order.

Also add a coverage-style assertion that every member of the current `ExprNode`
union is either covered by child traversal or explicitly classified as a leaf or
specialized form. This is the guard against repeating the current missed-form
pattern.

- [ ] **Step 2: Run traversal tests and confirm they fail**

Run:

```bash
pytest tests/test_workflow_lisp_expressions.py -q
```

Expected: failure because `expression_traversal.py` does not exist yet.

- [ ] **Step 3: Implement `expression_traversal.py`**

Implement minimal helpers:

```python
def iter_child_exprs(expr: ExprNode) -> tuple[ExprNode, ...]:
    ...

def walk_expr(expr: ExprNode) -> Iterator[ExprNode]:
    ...
```

Keep the module dependency one-way: it may import expression dataclasses, but it
must not import compiler, typecheck, lowering, or workflows.

- [ ] **Step 4: Migrate low-risk walkers**

Use `iter_child_exprs` first in:

- function dependency scanning in `functions.py`;
- provider/prompt extern collection in the lowering facade;
- ProcRef specialization discovery in `compiler.py`, only where it preserves
  current ProcRef environment handling.
- workflow extern collection in `workflow_refs.py`, if doing so is mechanical;
- let-proc escape or value-use checks in `typecheck.py`, only if the scoped
  behavior remains obvious.

Do not force every walker into the helper if a walker carries special scoped
state that would make the helper confusing.

- [ ] **Step 5: Run focused tests**

Run:

```bash
pytest \
  tests/test_workflow_lisp_functions.py \
  tests/test_workflow_lisp_workflow_refs.py \
  tests/test_workflow_lisp_lowering.py \
  -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

If package split was chosen:

```bash
git add orchestrator/workflow_lisp/expression_traversal.py orchestrator/workflow_lisp/functions.py orchestrator/workflow_lisp/lowering orchestrator/workflow_lisp/compiler.py tests/test_workflow_lisp_expressions.py
git commit -m "refactor: share workflow lisp expression traversal"
```

If package split was deferred:

```bash
git add orchestrator/workflow_lisp/expression_traversal.py orchestrator/workflow_lisp/functions.py orchestrator/workflow_lisp/lowering.py orchestrator/workflow_lisp/compiler.py tests/test_workflow_lisp_expressions.py
git commit -m "refactor: share workflow lisp expression traversal"
```

## Task 4: Extract Lowering Extern Collection

**Files:**
- Create if package split was chosen: `orchestrator/workflow_lisp/lowering/externs.py`
- Create if package split was deferred: `orchestrator/workflow_lisp/lowering_externs.py`
- Modify if package split was chosen: `orchestrator/workflow_lisp/lowering/__init__.py`
- Modify if package split was deferred: `orchestrator/workflow_lisp/lowering.py`
- Test: existing lowering/structured-result tests

- [ ] **Step 1: Move extern collection helpers**

Move provider and prompt discovery out of the lowering facade, including the
helper currently responsible for collecting required provider and prompt extern
names from typed workflows and procedures.

The new module should expose a narrow function, for example:

```python
def collect_required_externs(
    typed_workflow: TypedWorkflowDef,
    *,
    typed_procedures: Mapping[str, TypedProcedureDef],
) -> tuple[set[str], set[str]]:
    ...
```

- [ ] **Step 2: Keep behavior identical**

Preserve:

- procedure recursion behavior;
- cycle guard behavior;
- handling for provider forms, phase forms, `produce-one-of`, and command args;
- returned provider/prompt name sets.

- [ ] **Step 3: Update imports**

Update the lowering facade to call the new helper. Avoid creating import cycles.

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_structured_results.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

If package split was chosen:

```bash
git add orchestrator/workflow_lisp/lowering
git commit -m "refactor: extract workflow lisp lowering extern discovery"
```

If package split was deferred:

```bash
git add orchestrator/workflow_lisp/lowering_externs.py orchestrator/workflow_lisp/lowering.py
git commit -m "refactor: extract workflow lisp lowering extern discovery"
```

## Task 5: Extract Lowering-Time Type Helpers

**Files:**
- Create if package split was chosen: `orchestrator/workflow_lisp/lowering/types.py`
- Create if package split was deferred: `orchestrator/workflow_lisp/lowering_types.py`
- Modify if package split was chosen: `orchestrator/workflow_lisp/lowering/__init__.py`
- Modify if package split was deferred: `orchestrator/workflow_lisp/lowering.py`
- Test: existing lowering/variant proof tests

- [ ] **Step 1: Move coherent helper cluster**

Extract helpers related to lowering-time type inference, such as:

- inline binding type inference;
- expression type resolution during lowering;
- match-arm binding type resolution.

Keep `_LoweringContext` ownership clear. If importing `_LoweringContext` would
create a bad cycle or expose too much private state, introduce a narrow protocol
or pass the specific pieces needed by the helper.

- [ ] **Step 2: Preserve error behavior**

Where existing helpers raise `LispFrontendCompileError`, preserve diagnostic
codes, spans, form paths, and expansion stacks.

Do not convert compiler diagnostics into raw `TypeError` or `ValueError`.

- [ ] **Step 3: Run focused tests**

Run:

```bash
pytest \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_variant_proofs.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Commit**

If package split was chosen:

```bash
git add orchestrator/workflow_lisp/lowering
git commit -m "refactor: extract workflow lisp lowering type helpers"
```

If package split was deferred:

```bash
git add orchestrator/workflow_lisp/lowering_types.py orchestrator/workflow_lisp/lowering.py
git commit -m "refactor: extract workflow lisp lowering type helpers"
```

## Task 6: Narrow Package Root Public API

**Files:**
- Modify: `orchestrator/workflow_lisp/__init__.py`
- Modify: tests that import internals from package root, if any

- [ ] **Step 1: Inventory package-root imports**

Run:

```bash
rg -n "from orchestrator\\.workflow_lisp import|import orchestrator\\.workflow_lisp" .
```

Classify each import as public facade use or internal implementation/test use.

- [ ] **Step 2: Define stable facade**

Keep only stable package-root exports unless an external caller requires more:

- `compile_stage1_module`
- `compile_stage3_module`
- `LispFrontendCompileError`
- `LispFrontendDiagnostic`
- `render_diagnostic`
- `render_diagnostics`

If an existing non-test caller uses another symbol from the root package, either
keep it temporarily with a comment or migrate that caller to the owning module.

- [ ] **Step 3: Update internal imports**

Tests and internal modules should import internals from concrete modules such as:

- `orchestrator.workflow_lisp.expressions`
- `orchestrator.workflow_lisp.type_env`
- `orchestrator.workflow_lisp.lowering`
- `orchestrator.workflow_lisp.workflows`

- [ ] **Step 4: Run import and test checks**

Run:

```bash
python -m compileall orchestrator/workflow_lisp
pytest tests/test_workflow_lisp_cli.py tests/test_workflow_lisp_build_artifacts.py -q
```

If feasible, also run:

```bash
pytest tests/test_workflow_lisp_* -q
```

- [ ] **Step 5: Commit**

```bash
git add orchestrator/workflow_lisp/__init__.py tests
git commit -m "refactor: narrow workflow lisp package facade"
```

## Task 7: Move Fixture-Only Runtime Closure Harness

**Files:**
- Move: `orchestrator/workflow_lisp/runtime_closure_design_fixtures.py`
- Create: `tests/support/workflow_lisp/runtime_closure_design_fixtures.py`
- Modify: `tests/test_workflow_lisp_runtime_closure_fixtures.py`
- Modify: any imports found by `rg runtime_closure_design_fixtures`

- [ ] **Step 1: Inventory imports**

Run:

```bash
rg -n "runtime_closure_design_fixtures" .
```

Confirm the module is test-only.

- [ ] **Step 2: Move the file**

Move the fixture harness under `tests/support/workflow_lisp/`.

Keep the module docstring stating that runtime closures remain deferred and this
is only a rejection-fixture harness.

- [ ] **Step 3: Update test imports**

Update tests to import from the new support module path.

- [ ] **Step 4: Run fixture tests**

Run:

```bash
pytest tests/test_workflow_lisp_runtime_closure_fixtures.py -q
```

Expected: pass.

- [ ] **Step 5: Run package compile check**

Run:

```bash
python -m compileall orchestrator/workflow_lisp
```

Expected: pass; production package no longer contains the fixture-only module.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/workflow_lisp tests/support tests/test_workflow_lisp_runtime_closure_fixtures.py
git commit -m "refactor: move workflow lisp runtime closure fixtures to tests"
```

## Task 8: Update Refactor Documentation

**Files:**
- Modify: `orchestrator/workflow_lisp/README.md`
- Modify: `docs/plans/2026-05-23-workflow-lisp-refactoring-backlog.md`

- [ ] **Step 1: Update package map**

Document the new module ownership:

- `expression_traversal.py`: shared expression walking;
- `lowering/`: package facade and extracted lowering helpers, if the package
  split was chosen;
- `lowering/externs.py` or `lowering_externs.py`: provider/prompt extern
  discovery;
- `lowering/types.py` or `lowering_types.py`: lowering-time type inference;
- `lowering.py` or `lowering/__init__.py`: workflow dictionary step emission
  facade.

- [ ] **Step 2: Update backlog status**

In the refactoring backlog, mark this tranche as addressing part of:

- split lowering responsibilities by operation family;
- characterize high-risk compiler behavior;
- module-level dependency audit;
- identify and retire migration scaffolding.

Do not claim the broader backlog is complete.

- [ ] **Step 3: Run docs/code smoke checks**

Run:

```bash
python -m compileall orchestrator/workflow_lisp
git diff --check
```

Expected: both pass.

- [ ] **Step 4: Commit**

```bash
git add orchestrator/workflow_lisp/README.md docs/plans/2026-05-23-workflow-lisp-refactoring-backlog.md
git commit -m "docs: record workflow lisp refactor ownership boundaries"
```

## Final Verification

After all tasks are complete, run:

```bash
python -m compileall orchestrator/workflow_lisp
pytest tests/test_workflow_lisp_* -q
git diff --check
```

If the full Workflow Lisp test selector is too slow or has unrelated failures,
record the narrower passing selectors and the reason full verification could not
be completed.

Before using the loop/phase-stdlib selectors as regression evidence, rerun:

```bash
python -m pytest tests/test_workflow_lisp_loop_recur.py tests/test_workflow_lisp_phase_stdlib.py -q
```

The module review observed `91 passed, 4 failed` on this selector. Either fix
those failures in an earlier tranche or record them as pre-existing failures
with current output.

## Expected Outcome

At the end of this tranche:

- repeated expression-tree walking is centralized enough to reduce missed-form
  risk;
- `lowering.py` is either converted to a package facade or has a documented
  deferral reason;
- lowering helper ownership is clearer, with extern discovery and type
  inference separated from step emission;
- fixture-only runtime-closure code is no longer in the production package;
- package-root imports expose a narrower stable facade;
- the existing compiler behavior, diagnostics, source maps, and generated
  workflow contracts remain unchanged.
