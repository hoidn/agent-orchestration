# Workflow Lisp Expression Traversal Prerequisite Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-expression-traversal-prerequisite`
Target design: `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the bounded prerequisite selected by the current
drain state before Track A follow-ons, parametric loop-state work, or later
stdlib review-loop work widen more duplicated expression walkers:

- add one shared frontend-owned expression-traversal surface at
  `orchestrator/workflow_lisp/expression_traversal.py`;
- define the exact contract for `iter_child_exprs(expr)` and `walk_expr(expr)`
  over the current `ExprNode` union;
- migrate only the first low-risk adopter set where traversal duplication is
  mechanical and scope handling can stay obvious;
- add coverage proving every current `ExprNode` union member is either handled
  by direct-child traversal or explicitly classified as a leaf expression;
- keep specialized walkers that carry local-value, proof, or lowering-scope
  semantics out of this slice unless they can reuse the helper without hiding
  those semantics.

Out of scope for this slice:

- generic visitor frameworks, callback registries, or a second expression IR;
- Track A imported `.orc` expansion, form-registry work, or review-loop bridge
  retirement;
- new Workflow Lisp syntax, type-system behavior, lowering semantics, or
  runtime behavior;
- typecheck-family or lowering-family decomposition beyond consuming the shared
  traversal helper where the behavior is plainly mechanical;
- command-adapter redesign, new scripts, runtime-native effects, or hidden
  command glue;
- backlog, run-state, queue, or progress-ledger edits.

This is a bounded implementation architecture for the selected prerequisite
only. It does not replace the parent frontend design, the accepted baseline
frontend contract, or the broader review/revise stdlib integration design.

## Problem Statement

The target design makes one refactor prerequisite explicit: later Track A,
loop-state, and stdlib review-loop work must stop adding or updating duplicated
expression walkers without one shared owner surface.

The current checkout still has that risk:

1. `orchestrator/workflow_lisp/expression_traversal.py` does not exist.
2. `functions.py::_function_dependencies(...)` recursively walks a small manual
   subset of expression shapes.
3. `compiler.py::_procedure_dependencies(...)` carries another handwritten
   recursion tree with overlapping but different coverage.
4. `workflow_refs.py::collect_workflow_extern_names(...)` carries a third
   manual recursion tree for provider and prompt extern discovery.
5. `procedure_specialization.py::discover_proc_ref_specializations(...)`
   contains a larger environment-sensitive walker that duplicates most of the
   same structural recursion.
6. `lowering/phase_scope.py::_workflow_extern_requirements(...)` carries
   another provider/prompt extern walker with same-file procedure recursion.
7. Additional manual walkers remain in `lowering/core.py`,
   `lowering/procedures.py`,
   `lowering/phase_drain.py`,
   `lowering/phase_flow.py`,
   and `lowering/phase_stdlib.py`, each with slightly different coverage and
   failure behavior.
8. `tests/test_workflow_lisp_expressions.py` currently checks that the legacy
   `ReviewReviseLoopExpr` no longer exists, but there is no coverage-style
   assertion that the current `ExprNode` union is fully traversed or explicitly
   classified.

The design problem is not that every walker must become identical. Some walkers
must keep special semantics such as local environment threading, same-file
procedure recursion, or proof-sensitive handling. The missing piece is smaller:

- one shared owner for direct child-expression enumeration;
- one fail-closed coverage contract for the current `ExprNode` union;
- one first adopter set proving downstream code can reuse that owner without
  hiding scoped behavior.

Without that prerequisite, later slices can still typecheck or lower new forms
correctly in one pass while silently missing them in dependency scanning,
extern discovery, ProcRef specialization discovery, or related analyses.

## Design Constraints

The implementation must stay coherent with:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - `8.1 Hard Preflight Before Track A`
  - `9.7 Introduce Shared Expression Traversal`
  - `9.7.1 Prerequisite Handoff Contract`
  - `24. Stage 1 - Behavior-Preserving Refactor Preflight`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `9. Pure Expressions`
  - `10. let*`
  - `11. Pattern Matching`
  - `13. Loops`
  - `22-30` for current high-level expression families
  - `59. Validation Sequence`
  - `74. Source Map Requirements`
- `docs/design/workflow_lisp_refactor_architecture.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/2026-06-02-workflow-lisp-low-hanging-refactor-plan.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/6/prerequisite-selector/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/6/design-gap-architect/architecture-targets.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/6/design-gap-architect/existing-architecture-index.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

The slice must preserve these guardrails:

- keep `orchestrator/workflow_lisp/` as the frontend-owned package and shared
  runtime semantics under `orchestrator/workflow/`;
- reuse the staged frontend pipeline:
  read -> syntax -> macro expansion -> definitions/procedures/workflows ->
  typecheck -> lowering -> shared validation;
- preserve current `.orc` surface semantics, diagnostics, spans, form paths,
  macro expansion stacks, source-map lineage, and compile-time-only ref rules;
- keep the traversal helper dependency one-way: it may depend on frontend
  expression and helper dataclasses, but it must not import compiler,
  typecheck, lowering, workflows, runtime, or shared-validation modules;
- keep structured state authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- keep command-backed surfaces explicit: traversal must visit child expressions
  inside `CommandResultExpr`, `ProviderResultExpr`, `ProduceOneOfExpr`, and
  related high-level forms rather than treating them as opaque leaves.

`docs/design/workflow_command_adapter_contract.md` is authoritative here even
though this slice adds no adapter. Several adopters analyze expressions that can
contain `command-result` or adapter-backed high-level forms. The shared helper
must not create a loophole where command-bearing nodes become invisible to
dependency scanning, extern discovery, or future validator-facing analyses.

`docs/steering.md` is empty in this checkout. That is not permission to widen
scope.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The full index in
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/6/design-gap-architect/existing-architecture-index.md`
was reviewed for coherence. The directly reused slices for this gap are:

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defun-pure-helper-surface/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/loop-recur-bounded-loops/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/track-a-form-registry-elaboration-boundary/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-owner-seam-split-prerequisite/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-lowering-core-family-decomposition/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parametric-loop-state-authoring/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-review-revise-preflight-hazard-fixes/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-typecheck-family-decomposition/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`

### Decisions Reused

- Reuse the staged frontend pipeline and package ownership split.
- Reuse the refactor architecture sequencing rule that shared traversal lands
  before broader package, registry, or semantic feature work.
- Reuse the current provenance substrate:
  `SourcePosition`,
  `SourceSpan`,
  recursive syntax objects,
  `LispFrontendDiagnostic`,
  macro expansion stacks,
  and existing lowering/source-map lineage surfaces.
- Reuse the hazard-fix slice's fail-closed rule: unknown or newly introduced
  expression containers must not silently disappear from analysis.
- Reuse the owner-seam and family-decomposition slices' distinction between
  shared mechanical helpers and higher-level walkers that still own scoped
  semantics.
- Reuse the compile-time-only ProcRef and WorkflowRef rules from the workflow
  refs and parametric specialization slices.

### New Decisions In This Slice

- Add one new shared owner module:
  `orchestrator/workflow_lisp/expression_traversal.py`.
- Keep that module intentionally narrow: it owns only direct-child expression
  enumeration and one generic pre-order `walk_expr(...)`.
- Treat direct-child traversal as the stable contract, not a fully generic
  visitor framework with callbacks, mutation hooks, or environment threading.
- Require the helper to cover the current full `ExprNode` union, including
  newer surfaces such as `BindProcExpr`, `LetProcExpr`,
  `WorkflowRefLiteralExpr`,
  `ProcRefLiteralExpr`,
  `GeneratedRelpathSeedExpr`,
  and the retained legacy `StdlibSpecializationExpr`.
- Limit the first adopter set to walkers where child recursion is mechanical:
  `functions.py`,
  `compiler.py`,
  `workflow_refs.py`,
  `procedure_specialization.py`,
  and `lowering/phase_scope.py`.
- Keep more semantically loaded walkers such as
  `functions.py::_find_purity_violation(...)`,
  `lowering/procedures.py::_procedure_private_call_site_analysis(...)`,
  `lowering/core.py::_typed_workflow_dependencies(...)`,
  `lowering/phase_drain.py::_workflow_extern_requirements(...)`,
  and `typecheck` scoped checks as explicit follow-on consumers, not mandatory
  first adopters.

### Conflicts Or Revisions

The low-hanging refactor plan named `compiler.py` as the ProcRef-specialization
adopter site. The current checkout has already moved that ownership into
`procedure_specialization.py`. This slice revises the adopter path narrowly:

- the shared traversal helper still serves ProcRef specialization discovery;
- the first adopter is the landed owner module
  `procedure_specialization.py`, not the old compiler facade;
- `compiler.py::_procedure_dependencies(...)` remains a separate mechanical
  adopter because it still owns a duplicated expression walk.

No shared concepts such as Core Workflow AST, Semantic Workflow IR, TypeCatalog,
SourceMap, pointer authority, or variant proof are redefined here.

## Ownership Boundaries

This slice owns:

- `orchestrator/workflow_lisp/expression_traversal.py`;
- the exact direct-child traversal contract for current `ExprNode` members;
- the coverage-style test contract proving current union coverage or explicit
  leaf classification;
- first-adopter migration of the selected low-risk walkers;
- focused tests proving traversal order and walker reuse stay behaviorally
  coherent.

This slice intentionally does not own:

- a general-purpose visitor or rewrite framework;
- source-code implementation of all existing duplicated walkers;
- redesign of ProcRef specialization, workflow extern rebinding, lowering
  dependency analysis, or purity semantics;
- lowering or typecheck family decomposition beyond consuming the helper where
  behavior is plainly mechanical;
- new scripts, adapters, runtime-native effects, or bridge-removal work.

## Current Checkout Facts

Fresh checkout evidence shows the prerequisite is still open and still narrow:

- `orchestrator/workflow_lisp/expression_traversal.py` is absent.
- `orchestrator/workflow_lisp/functions.py` still contains manual recursive
  traversal in `_function_dependencies(...)`.
- `orchestrator/workflow_lisp/compiler.py` still contains manual recursive
  traversal in `_procedure_dependencies(...)`.
- `orchestrator/workflow_lisp/workflow_refs.py` still contains manual recursive
  traversal in `collect_workflow_extern_names(...)`.
- `orchestrator/workflow_lisp/procedure_specialization.py` still contains a
  large recursive walker in `discover_proc_ref_specializations(...)`, with
  environment handling layered on top of structural recursion.
- `orchestrator/workflow_lisp/lowering/phase_scope.py` still contains manual
  provider/prompt extern recursion in `_workflow_extern_requirements(...)`.
- additional duplicated structural recursion remains in:
  `orchestrator/workflow_lisp/lowering/core.py`,
  `orchestrator/workflow_lisp/lowering/procedures.py`,
  `orchestrator/workflow_lisp/lowering/phase_drain.py`,
  `orchestrator/workflow_lisp/lowering/phase_flow.py`, and
  `orchestrator/workflow_lisp/lowering/phase_stdlib.py`.
- `tests/test_workflow_lisp_expressions.py` has no traversal coverage
  assertions yet.
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` remains empty, so
  no later implementation event supersedes the selected prerequisite.

The checkout also shows that the target design's original expression list is no
longer complete for current code. The helper and its coverage tests must account
for the current union as authored today, not only the earlier design examples.

## Proposed Package Boundary

Add one new narrow module and update only the first adopter set:

```text
orchestrator/workflow_lisp/
  expression_traversal.py     # new shared owner
  compiler.py                 # adopter
  functions.py                # adopter
  procedure_specialization.py # adopter
  workflow_refs.py            # adopter
  lowering/
    phase_scope.py            # adopter

tests/
  test_workflow_lisp_expressions.py
  test_workflow_lisp_functions.py
  test_workflow_lisp_workflow_refs.py
  test_workflow_lisp_procedures.py
  test_workflow_lisp_lowering.py
```

The new module may import:

- `ExprNode` and the frontend expression dataclasses from `expressions.py`;
- frontend-owned helper dataclasses referenced from expression fields, such as
  `MatchArm`,
  `BindProcBinding`,
  `LetProcBinding`,
  `ProduceOneOfProducerSpec`,
  `ProduceOneOfCandidateSpec`,
  `ProduceOneOfCandidateFieldSpec`,
  `ResourceTransitionSpec`,
  `FinalizeSelectedItemSpec`,
  and `BacklogDrainSpec`.

It must not import:

- `compiler.py`
- `procedure_specialization.py`
- `typecheck*.py`
- `lowering/*`
- shared runtime or validation packages

## Traversal Contract

### Public Helper Surface

The shared owner surface is:

```python
def iter_child_exprs(expr: ExprNode) -> tuple[ExprNode, ...]:
    ...


def walk_expr(expr: ExprNode) -> Iterator[ExprNode]:
    ...
```

Contract:

- `iter_child_exprs(...)` returns only direct child `ExprNode` values.
- Returned children preserve stable authored order.
- `walk_expr(...)` is a deterministic pre-order traversal:
  node first, then descendants through `iter_child_exprs(...)`.
- The helper is structural only. It does not carry environments, proof facts,
  local values, or callee expansion behavior.
- Unknown or newly introduced expression containers must fail closed in tests
  through explicit coverage assertions rather than silently acting like leaves.

### Direct-Child Coverage

The helper must cover every current `ExprNode` case.

Leaf expressions:

- `NameExpr`
- `LiteralExpr`
- `FieldAccessExpr`
- `PhaseTargetExpr`
- `GeneratedRelpathSeedExpr`
- `WorkflowRefLiteralExpr`
- `ProcRefLiteralExpr`

Direct-child traversal must cover at least:

- `RecordExpr`
- `UnionVariantExpr`
- `LetStarExpr`
- `IfExpr`
- `MatchExpr`
- `CallExpr`
- `FunctionCallExpr`
- `ProcedureCallExpr`
- `WithPhaseExpr`
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

The implementation may traverse through non-`ExprNode` helper carriers where
required, but only to expose contained child expressions. It must not promote
those helper carriers into a second public expression hierarchy.

### Fail-Closed Coverage Proof

The tests for this slice should compare the current `ExprNode` union members
against the helper's explicit classification so future expression additions fail
visibly until the shared helper is updated.

That proof is the acceptance gate that turns "remember to update every walker"
into one obvious owner update point.

## First Adopter Migrations

### 1. `functions.py::_function_dependencies(...)`

Use `walk_expr(...)` directly and collect `FunctionCallExpr.callee_name`.

Reason:

- this walker is purely structural;
- it does not thread scope or local values;
- replacing handwritten recursion here is low-risk and directly proves the
  helper is usable outside lowering.

### 2. `compiler.py::_procedure_dependencies(...)`

Use `walk_expr(...)` directly and collect `ProcedureCallExpr.callee_name`.

Reason:

- this walker is also purely structural;
- current manual coverage is incomplete relative to the current `ExprNode`
  union;
- the helper reduces one more duplicated recursion tree without touching
  specialization or lowering semantics.

### 3. `workflow_refs.py::collect_workflow_extern_names(...)`

Keep node-specific provider/prompt collection logic for:

- `ProviderResultExpr`
- `RunProviderPhaseExpr`
- `ProduceOneOfExpr`

Delegate the generic child recursion to `iter_child_exprs(...)`.

Reason:

- this preserves the explicit extern-name collection semantics;
- only the structural descent becomes shared;
- this is the design's named "workflow extern collection if mechanical" case.

### 4. `procedure_specialization.py::discover_proc_ref_specializations(...)`

Keep special handling for:

- `ProcedureCallExpr`
- `LetStarExpr`
- binding-time ProcRef environment extension

Delegate generic descent for the remaining node kinds to
`iter_child_exprs(...)`.

Reason:

- this preserves the current ProcRef environment semantics;
- it removes duplicated structural recursion from the longest current walker;
- it directly satisfies the target design's "ProcRef specialization discovery
  where current environment handling is preserved" clause.

### 5. `lowering/phase_scope.py::_workflow_extern_requirements(...)`

Keep special handling for:

- `ProviderResultExpr`
- `RunProviderPhaseExpr`
- `ProduceOneOfExpr`
- recursive same-file `ProcedureCallExpr` descent

Delegate generic child descent to `iter_child_exprs(...)`.

Reason:

- this is the current lowering-owned provider/prompt extern collector;
- it proves the helper can be consumed in lowering without collapsing
  scope-specific behavior;
- it is still bounded because the helper does not take ownership of same-file
  procedure recursion.

## Deferred Walkers

The following walkers are intentionally not required first adopters for this
slice:

- `functions.py::_find_purity_violation(...)`
- `lowering/procedures.py::_procedure_private_call_site_analysis(...)`
- `lowering/core.py::_typed_workflow_dependencies(...)`
- `lowering/phase_drain.py::_workflow_extern_requirements(...)`
- `lowering/phase_drain.py::_find_first_nameexpr(...)`
- `lowering/phase_flow.py::_provider_metadata_names(...)`
- any `typecheck` let-proc escape or value-use analysis

Reason:

- they carry more than structural recursion;
- some recurse through resolved local values or same-file procedure bodies;
- some operate on mixed `ExprNode` plus non-expression value graphs;
- the target design allows deferring scoped walkers until the helper's shared
  owner surface is in place and the scoped behavior stays obvious.

Deferral here is not a rejection of future reuse. It is a bounded-scope rule:
this prerequisite lands the shared update point first, then later slices may
adopt it where the semantics are still explicit.

## Verification Strategy

Add focused tests that prove both the helper contract and the selected adopter
set:

- `tests/test_workflow_lisp_expressions.py`
  - direct-child order for representative forms;
  - coverage assertion for current `ExprNode` union members;
  - leaf classification for childless expressions.
- `tests/test_workflow_lisp_functions.py`
  - helper dependency scanning still finds nested pure-helper calls through the
    current expression families.
- `tests/test_workflow_lisp_workflow_refs.py`
  - extern collection still discovers provider/prompt names through nested
    record, loop, and phase-helper expressions.
- `tests/test_workflow_lisp_procedures.py`
  - ProcRef specialization discovery still finds compile-time specializations
    across nested structural forms.
- `tests/test_workflow_lisp_lowering.py`
  - lowering extern requirements still discover provider/prompt usage through
    same-file procedures and nested phase-helper expressions.

Required command evidence for this prerequisite:

```bash
pytest tests/test_workflow_lisp_expressions.py -q
pytest tests/test_workflow_lisp_functions.py -q
pytest tests/test_workflow_lisp_workflow_refs.py -q
pytest tests/test_workflow_lisp_procedures.py -q
pytest tests/test_workflow_lisp_lowering.py -q
python -m compileall orchestrator/workflow_lisp
git diff --check
```

If broader Workflow Lisp selectors are needed because the touched adopters share
fixtures or helper imports, record the narrower failure first and then widen
only as required by fresh evidence.

## Expected Outcome

After this slice lands:

- Workflow Lisp has one obvious owner surface for structural expression
  traversal;
- new `ExprNode` variants fail loudly until that surface is updated;
- the first adopter set proves the helper can be reused across functions,
  compiler, specialization, workflow-ref analysis, and lowering without hiding
  scoped behavior;
- blocked follow-on work such as
  `workflow-lisp-parametric-loop-state-authoring`
  can cite one landed owner path instead of widening duplicated recursion again.
