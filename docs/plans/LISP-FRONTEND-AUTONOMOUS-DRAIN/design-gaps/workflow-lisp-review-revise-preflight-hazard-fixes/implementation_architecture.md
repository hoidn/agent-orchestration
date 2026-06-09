# Workflow Lisp Review/Revise Preflight Hazard Fixes Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-review-revise-preflight-hazard-fixes`
Target design: `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_mvp_specification.md`

## Scope

This slice covers exactly the hard-preflight hazard fixes selected by the drain
state before Track A generic `.orc` expansion work:

- remove the shadowed duplicate helper definitions in
  `orchestrator/workflow_lisp/lowering.py`;
- resolve the missing `VariantCaseTypeRef` reference used by lowering-time
  private-workflow type analysis;
- make `defun` purity validation fail closed for unknown `ExprNode`
  containers instead of silently treating them as pure;
- guard macro hygiene shape assumptions so malformed expanded `match` and
  `defworkflow` forms preserve provenance and reach owned validators instead of
  raising uncaught indexing errors;
- add only the focused regression coverage needed to prove these fixes are
  behavior-preserving.

Out of scope for this slice:

- shared expression traversal extraction;
- the lowering package/facade split;
- `TypecheckContext` or other broad context refactors;
- Track A form registry, denylist tests, imported `.orc` expansion, or generic
  ProcRef specialization;
- removal of `ReviewReviseLoopExpr`, `_validate_review_loop_result_contract`,
  `__stdlib-specialization__`, or any other review-loop de-specialization work;
- new Workflow Lisp language features, runtime behavior changes, command-step
  semantics, or spec deltas.

This is a bounded implementation architecture for the preflight hazard-fix gap
only. It does not replace the parent frontend design, the broader refactor
architecture, or the follow-on review-loop stdlib migration architecture.

## Problem Statement

The target integration design treats these fixes as the first hard prerequisite
before Track A because the current checkout can drift semantically even without
adding a new language feature.

The hazards are concrete:

1. `lowering.py` defines `_origin_for_workflow`,
   `_procedure_provenance_notes`, and `_definition_only_module` twice. Python
   silently keeps the later definition, which means future edits to the earlier
   copies can look correct in review while having no effect at runtime.
2. `lowering.py` performs private-workflow type analysis against
   `VariantCaseTypeRef` but does not import that type from `type_env.py`. That
   makes one real lowering path depend on an accidental missing symbol rather
   than the frontend's existing type authority.
3. `functions.py::_find_purity_violation(...)` returns `None` for any
   unclassified `ExprNode`. New effectful or composite expression forms can
   therefore slip through `defun` purity validation until some later pass fails
   less clearly.
4. `macros.py` contains hygiene handlers that index into `match` and
   `defworkflow` shapes directly. When malformed macro output reaches those
   handlers, the compiler can raise an uncaught `IndexError` or similar Python
   failure before the normal elaboration/typecheck diagnostics report the
   authored problem with macro provenance.

The selector rationale also notes broader review-loop debt still present in the
checkout, including the special review-loop typecheck path and the stdlib
`__stdlib-specialization__` export route. Those remain real migration blockers,
but they are not owned by this slice. This preflight document intentionally
stops at hazard removal so Track A can start from a safer baseline rather than
mixing cleanup and architecture replacement in one patch.

## Design Constraints

The implementation must stay coherent with:

- `docs/index.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - `8. Refactor Prerequisite Model`
  - `9. Hard Preflight: Behavior-Preserving Refactor Tranche`
  - `9.1 Fix Concrete Hazards`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
- `docs/design/workflow_lisp_refactor_architecture.md`
- `docs/plans/2026-06-02-workflow-lisp-low-hanging-refactor-plan.md`
- `docs/plans/2026-06-02-workflow-lisp-generic-orc-expansion-refactor.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/steering.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/selector/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/architecture-targets.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/existing-architecture-index.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

The slice must also preserve these guardrails:

- keep `orchestrator/workflow_lisp/` as the frontend-owned package and keep
  shared runtime semantics under `orchestrator/workflow/`;
- reuse the current staged frontend pipeline:
  read -> syntax -> macro expansion -> definitions/functions/procedures/
  workflows -> typecheck -> lowering -> shared validation;
- preserve `SourcePosition`, `SourceSpan`, recursive syntax provenance,
  `LispFrontendDiagnostic`, macro expansion stacks, and `LoweringOriginMap`
  instead of inventing parallel provenance channels;
- keep the fixes behavior-preserving: no authored `.orc` syntax changes, no
  runtime behavior changes, no relaxed diagnostics, and no weakening of source
  maps or effect visibility;
- keep structured state and typed artifacts authoritative; do not introduce
  inline semantic shell or Python glue while fixing purity, macro, or lowering
  hazards.

`docs/design/workflow_command_adapter_contract.md` remains authoritative here
even though this slice does not add a command boundary. The purity and macro
fixes must not create loopholes where command-backed or stdlib-backed effects
hide inside an allegedly pure helper or a macro-generated malformed form.

`docs/steering.md` is empty in this checkout. That is not permission to widen
scope. The selector bundle and target design remain the effective steering
surfaces.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The full index in
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/existing-architecture-index.md`
was reviewed for coherence. The directly reused slices for this gap are:

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defun-pure-helper-surface/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/hygienic-defmacro-system/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-validation-diagnostics-pipeline/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/module-import-export-resolution/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/loop-recur-bounded-loops/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`

### Decisions Reused

- Reuse the existing frontend/runtime package split and staged pipeline.
- Reuse the current provenance substrate:
  `SourcePosition`,
  `SourceSpan`,
  recursive syntax objects,
  expansion stacks,
  `LispFrontendDiagnostic`,
  and lowering-origin remapping.
- Reuse the `defun` architecture's rule that purity is a hard authored
  contract and must reject effectful or unsupported expression shapes instead
  of deferring silently.
- Reuse the macro architecture's rule that malformed macro output must preserve
  provenance and then fail through owned elaboration/typecheck diagnostics,
  not uncaught Python exceptions.
- Reuse the refactor architecture's sequencing rule that concrete hazard fixes
  land before shared traversal extraction, context-object work, or lowering
  package splitting.
- Reuse the existing `type_env.py` type authority, including
  `VariantCaseTypeRef`, rather than introducing local lowering-only type
  substitutes.

### New Decisions In This Slice

- Treat the later effective duplicate helper bodies in `lowering.py` as the
  canonical semantics, because that is the behavior Python currently executes.
  Earlier shadowed copies are removed rather than merged into a third variant.
- Keep the `VariantCaseTypeRef` repair minimal: import and reuse the existing
  type reference where lowering already assumes it, without reopening private
  workflow design.
- Make unknown `ExprNode` containers in `_find_purity_violation(...)` a
  blocking frontend condition rather than a silent "pure" default.
- Guard macro hygiene handlers by shape-checking before positional indexing and
  by falling back to provenance-preserving ordinary syntax traversal when a
  malformed `match` or `defworkflow` cannot be hygienically rewritten safely.

### Conflicts Or Revisions

The phase-context stdlib and review-loop migration documents describe later
removal of review-loop-specific compiler branches. This slice does not revise
that target. It explicitly defers:

- `ReviewReviseLoopExpr` removal;
- `_validate_review_loop_result_contract` removal;
- `std/phase.orc` de-specialization away from `__stdlib-specialization__`;
- Track A form registry and denylist work.

The only revision here is sequencing: those larger changes must continue to
wait until the concrete hazards named in the integration design are removed.

## Ownership Boundaries

This slice owns:

- duplicate-helper cleanup in `orchestrator/workflow_lisp/lowering.py`;
- the missing `VariantCaseTypeRef` import and any tiny supporting lowering
  adjustments required for that path to use the existing type authority;
- fail-closed `defun` purity handling in
  `orchestrator/workflow_lisp/functions.py`;
- macro hygiene shape guards in `orchestrator/workflow_lisp/macros.py`;
- focused regression tests in the narrowest relevant Workflow Lisp test modules.

This slice intentionally does not own:

- `typecheck.py` review-loop special-contract removal;
- `std/phase.orc` macro or specialization redesign;
- generic expression traversal extraction or `walk_expr(...)` introduction;
- lowering package/facade restructuring;
- form-registry or imported-stdlib expansion architecture;
- new diagnostics pipeline architecture beyond the minimal codes or metadata
  required for the selected hazards.

## Current Checkout Facts

The current checkout confirms the selected hazards directly:

- `orchestrator/workflow_lisp/lowering.py` defines
  `_origin_for_workflow(...)` twice,
  `_procedure_provenance_notes(...)` twice,
  and `_definition_only_module(...)` twice.
- The later `_origin_for_workflow(...)` and
  `_procedure_provenance_notes(...)` bodies preserve helper and let-proc
  provenance notes that the earlier copies do not, so the later bodies are the
  current runtime behavior and must remain authoritative during cleanup.
- `orchestrator/workflow_lisp/lowering.py` references `VariantCaseTypeRef` in
  lowering-time field projection logic while importing `RecordTypeRef` and
  `WorkflowRefTypeRef` but not `VariantCaseTypeRef`.
- `orchestrator/workflow_lisp/functions.py::_find_purity_violation(...)`
  ends in a bare `return None`, which treats any future unclassified
  `ExprNode` as pure.
- `orchestrator/workflow_lisp/macros.py` uses positional indexing in
  `_hygienic_match(...)` and `_hygienic_defworkflow(...)` after dispatching on
  head name, which means malformed expanded shapes can fail inside hygiene
  before normal elaboration reports the actual authored error.
- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` still exports
  `review-revise-loop` through `__stdlib-specialization__`, and
  `orchestrator/workflow_lisp/typecheck.py` still contains
  `_validate_review_loop_result_contract(...)`; those are acknowledged context
  only, not work items for this slice.
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` contains no
  events, so there is no later recorded implementation state superseding the
  selected preflight gap.

## Proposed Package Boundary

No package restructuring occurs in this slice. The implementation stays inside
the existing modules that already own the affected behavior:

```text
orchestrator/workflow_lisp/
  functions.py
  lowering.py
  macros.py
  type_env.py          # reused authority only

tests/
  test_workflow_lisp_functions.py
  test_workflow_lisp_macros.py
  test_workflow_lisp_lowering.py
  test_workflow_lisp_procedures.py   # only if the private-workflow regression fits best here
```

Responsibilities:

- `functions.py`
  - keep authored purity validation authoritative for `defun`;
  - reject unsupported or newly introduced expression containers
    deterministically.
- `macros.py`
  - keep hygiene syntax-only;
  - preserve expansion provenance when malformed expanded forms fall through to
    later validators.
- `lowering.py`
  - keep the existing lowering/runtime bridge authoritative;
  - remove dead shadowed helper copies;
  - reuse `VariantCaseTypeRef` from the type environment.
- tests
  - prove the fixes are behavior-preserving and catch regression back to
    shadowed helpers, fail-open purity, or uncaught macro-shape crashes.

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/spans.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/workflows.py`
- shared workflow validation/runtime modules under `orchestrator/workflow/`

## Hazard Remediation Plan

### 1. Remove Shadowed Lowering Helpers

Delete the earlier duplicate definitions of:

- `_procedure_provenance_notes(...)`
- `_origin_for_workflow(...)`
- `_definition_only_module(...)`

The later definitions remain the source of truth because they are the functions
Python currently binds at import time. This keeps the cleanup behavior-
preserving and makes future edits visible.

Do not:

- merge the earlier and later implementations into a new hybrid without a
  demonstrated behavioral need;
- move the helpers into a new module in this slice;
- treat duplicate cleanup as permission to reorganize unrelated lowering code.

### 2. Repair The Missing `VariantCaseTypeRef` Dependency

Lowering-time private-workflow analysis must import and reuse
`VariantCaseTypeRef` from `type_env.py` directly.

This fix is intentionally minimal:

- no new lowering-local type wrapper;
- no new typecheck pass;
- no redesign of private workflow signatures or variant proof;
- only enough code change for the existing lowering logic to refer to the same
  frontend type authority already used elsewhere.

The supporting regression should exercise a private-workflow or generated-call
path that reaches variant-case field analysis so the import cannot regress
silently.

### 3. Make `defun` Purity Fail Closed

`_find_purity_violation(...)` must stop using "unknown means pure" behavior.

Required behavior:

- every currently supported pure or effectful `ExprNode` variant remains
  classified explicitly;
- an unclassified container becomes a blocking result, not `None`;
- `_validate_pure_function_expr(...)` must surface that condition as an owned
  frontend diagnostic rather than an assertion or a later unrelated failure.

The implementation may use either:

- a dedicated purity diagnostic such as
  `unknown_exprnode_not_classified` / `function_purity_unknown_exprnode`; or
- another explicit unsupported-expression diagnostic with the same fail-closed
  semantics.

What matters architecturally is the failure mode:

- adding a new expression form without updating purity validation must fail the
  pure-helper check immediately;
- it must not silently permit effectful semantics inside `defun`.

This slice does not yet introduce the shared expression traversal utility from
the later refactor step. The purity checker may remain local, but it must no
longer fail open.

### 4. Guard Macro Hygiene Shape Assumptions

The hygiene layer must stop assuming that any list with head `match` or
`defworkflow` already has the full valid shape.

Required behavior:

- guard list length and child-node shape before indexing positional items in
  `_hygienic_match(...)` and `_hygienic_defworkflow(...)`;
- if the shape is malformed, preserve the expanded syntax and provenance rather
  than raising an uncaught indexing error;
- let the existing elaboration/typecheck validators reject the malformed form
  through normal diagnostics after hygiene returns a safe syntax tree.

The preferred failure mode is:

```text
macro expansion preserves expansion stack
  -> hygiene applies only safe recursive rewriting
  -> expressions/workflows elaboration reports owned parse/shape diagnostic
```

not:

```text
macro expansion
  -> hygiene indexes missing list item
  -> Python exception escapes without authored diagnostic
```

This guard work is intentionally narrow. It does not redesign hygiene or add a
generic malformed-syntax recovery framework.

## Focused Regression Surface

The slice should add or update the narrowest tests that lock the hazards down:

- `tests/test_workflow_lisp_functions.py`
  - a pure-helper regression proving an unknown or newly unsupported expression
    shape becomes a blocking diagnostic rather than compiling as pure;
- `tests/test_workflow_lisp_macros.py`
  - malformed macro expansions that produce bad `match` and bad `defworkflow`
    forms preserve macro provenance and fail through owned diagnostics instead
    of uncaught Python exceptions;
- `tests/test_workflow_lisp_lowering.py`
  - a regression that reaches the private-workflow variant-case lowering path
    and proves the missing `VariantCaseTypeRef` dependency is resolved;
- `tests/test_workflow_lisp_procedures.py`
  - optional only if the most natural private-workflow regression already lives
    in the procedure tests.

Do not add snapshot tests for the whole lowered workflow when a narrower
semantic assertion is enough.

## Acceptance Conditions

This slice is complete when all of the following are true:

- `lowering.py` no longer contains duplicate live definitions for
  `_procedure_provenance_notes(...)`,
  `_origin_for_workflow(...)`,
  or `_definition_only_module(...)`;
- lowering-time private-workflow field analysis resolves `VariantCaseTypeRef`
  through the shared frontend type authority;
- `_find_purity_violation(...)` no longer treats unknown `ExprNode`
  containers as pure;
- malformed macro-expanded `match` and `defworkflow` shapes no longer escape as
  uncaught Python indexing failures;
- the fixes do not remove or redesign the current review-loop special path;
- the package boundary remains unchanged and no unrelated refactor work is
  mixed into the hazard patch.

## Verification Strategy

The implementation must be verified with a focused suite that matches the
selected gap rather than the broader Track A backlog:

1. `python -m compileall orchestrator/workflow_lisp`
2. `python -m pytest --collect-only tests/test_workflow_lisp_functions.py tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_procedures.py -q`
3. `python -m pytest tests/test_workflow_lisp_functions.py tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_procedures.py -q`
4. `git diff --check`

If one of the listed test modules does not end up owning a new regression, the
implementation plan may drop that selector only with an explicit reason
recorded alongside the plan. The verification contract stays narrow on purpose:
these are preflight hazard fixes, not the later characterization or Track A
promotion suite.
