# Workflow Lisp Review/Revise Preflight Hazard Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the selected preflight hazards in the current Workflow Lisp checkout so Track A generic `.orc` expansion can start from a behavior-preserving baseline with no duplicate live lowering helpers, no missing lowering-time type authority import, no fail-open `defun` purity gap, and no macro-hygiene crash path for malformed expanded `match` or `defworkflow` forms.

**Architecture:** Keep the fix entirely inside the existing frontend-owned modules in `orchestrator/workflow_lisp/`. Preserve the current staged pipeline and current authored behavior while making four narrow repairs: keep only the later effective helper bodies in `lowering.py`, reuse `VariantCaseTypeRef` from `type_env.py` where lowering already depends on it, make helper purity reject unknown `ExprNode` containers instead of silently accepting them, and shape-guard macro hygiene so malformed expanded syntax falls through to owned elaboration/typecheck diagnostics with provenance intact.

**Tech Stack:** Python 3, `orchestrator/workflow_lisp`, shared `orchestrator.workflow` validation/runtime surfaces, pytest, `ast`/module-source inspection for a narrow duplicate-definition regression, and the exact verification command list recorded in `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/check_commands.json`.

---

## Fixed Inputs

Read these before implementation and treat them as authority:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
- `docs/design/workflow_lisp_refactor_architecture.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - `8. Refactor Prerequisite Model`
  - `9. Hard Preflight: Behavior-Preserving Refactor Tranche`
  - `9.1 Fix Concrete Hazards`
- `docs/plans/2026-06-02-workflow-lisp-low-hanging-refactor-plan.md`
- `docs/plans/2026-06-02-workflow-lisp-generic-orc-expansion-refactor.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-review-revise-preflight-hazard-fixes/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

Reference these implementation seams before editing:

- `orchestrator/workflow_lisp/functions.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/macros.py`
- `orchestrator/workflow_lisp/type_env.py`
- `tests/test_workflow_lisp_functions.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_macros.py`
- `tests/test_workflow_lisp_procedures.py`

## Current Repo Baseline

Assume this exact starting point:

- `docs/steering.md` is empty in this checkout and does not widen scope.
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` is still `{"ledger_version":1,"events":[]}`.
- `orchestrator/workflow_lisp/lowering.py` defines `_origin_for_workflow`, `_procedure_provenance_notes`, and `_definition_only_module` twice; Python currently executes the later copies.
- The later `_origin_for_workflow` and `_procedure_provenance_notes` bodies preserve helper and let-proc provenance notes that the earlier copies do not, so the later bodies are the canonical behavior to keep.
- `orchestrator/workflow_lisp/lowering.py` references `VariantCaseTypeRef` in private-workflow union/field projection logic without importing it from `type_env.py`.
- `orchestrator/workflow_lisp/functions.py::_find_purity_violation(...)` ends in a bare `return None`, so an unclassified future `ExprNode` is silently treated as pure.
- `orchestrator/workflow_lisp/macros.py::_hygienic_match(...)` and `_hygienic_defworkflow(...)` index into `datum.items[...]` before proving the expanded shape is large enough, so malformed expanded syntax can raise uncaught Python exceptions before owned validators run.
- Existing tests already cover the nearby surfaces that must remain stable:
  - helper normalization and purity behavior in `tests/test_workflow_lisp_functions.py`
  - malformed/hidden-effect macro behavior in `tests/test_workflow_lisp_macros.py`
  - private-workflow union-match lowering in `tests/test_workflow_lisp_procedures.py`

Execution rule for this plan: if the checkout diverges during implementation, the approved implementation architecture and the failing tests written from this plan win. Do not widen ownership into Track A or review-loop de-specialization just to make a failure disappear.

## Hard Scope Limits

Implement only the bounded `workflow-lisp-review-revise-preflight-hazard-fixes` slice:

- remove the shadowed duplicate live definitions for `_origin_for_workflow`, `_procedure_provenance_notes`, and `_definition_only_module` in `orchestrator/workflow_lisp/lowering.py`;
- import and reuse `VariantCaseTypeRef` from `orchestrator/workflow_lisp/type_env.py` in the private-workflow lowering path that already depends on it;
- make `functions.py::_find_purity_violation(...)` fail closed on unknown `ExprNode` containers;
- guard macro hygiene shape assumptions for malformed expanded `match` and `defworkflow` forms so provenance survives and owned diagnostics report the problem;
- add only the narrow regression tests needed to prove those fixes.

Explicit non-goals:

- no shared expression traversal extraction;
- no lowering package/facade split;
- no `TypecheckContext` or other broad context-object work;
- no Track A form registry, denylist tests, imported `.orc` expansion, or generic ProcRef specialization;
- no review-loop typecheck/lowering de-specialization;
- no stdlib `review-revise-loop` redesign;
- no new runtime/spec behavior, command adapters, or migration-policy work.

## Locked Decisions

Do not re-decide these during implementation.

Duplicate-helper cleanup contract:

- Keep the later effective implementations of `_origin_for_workflow`, `_procedure_provenance_notes`, and `_definition_only_module`.
- Delete the earlier shadowed copies rather than merging bodies into a third variant.
- Add one focused regression that inspects `lowering.py` as Python source and proves each affected helper is defined exactly once after the patch.

Lowering type-authority contract:

- Reuse `VariantCaseTypeRef` from `type_env.py`; do not create a lowering-local surrogate.
- Keep the existing private-workflow lowering logic and metadata-based routing intact; this is an import repair, not a redesign of private workflows.
- Reuse or minimally extend the existing private-workflow union-match regression in `tests/test_workflow_lisp_procedures.py` instead of inventing a broad new fixture family.

Purity fail-closed contract:

- Keep `_validate_pure_function_expr(...)` as the reporting entrypoint and keep the diagnostic code `pure_function_has_effect`.
- Make `_find_purity_violation(...)` return a blocking violation for any unknown `ExprNode` container instead of returning `None`.
- The violation text for unknown containers must mention that the helper body contains an unsupported expression container; do not silently classify it as pure.

Macro hygiene contract:

- `_hygienic_match(...)` and `_hygienic_defworkflow(...)` must prove the minimum positional shape before indexing fixed positions.
- If the expanded syntax is malformed, hygiene must fall back to provenance-preserving ordinary recursive traversal or return the malformed node unchanged except for safe child recursion; it must not synthesize structure or raise `IndexError`.
- Downstream elaboration/typecheck remains the owner of the authored diagnostic. The regression tests must assert an owned `LispFrontendCompileError` diagnostic is raised instead of an uncaught Python exception.

Verification contract:

- If you add or rename tests, run `pytest --collect-only` on the touched modules before the full test run.
- The final verification must use the exact ordered command list from `check_commands.json` with no substitutions or reordering.

## File Ownership

Modify:

- `orchestrator/workflow_lisp/functions.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/macros.py`
- `tests/test_workflow_lisp_functions.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_macros.py`
- `tests/test_workflow_lisp_procedures.py`

Reuse without broadening ownership:

- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/syntax.py`
- shared workflow validation/runtime modules under `orchestrator/workflow/`

Modify `type_env.py` only if a focused failing test proves an existing export/import surface is missing. This slice should not move ownership there.

## Task 1: Lock Regressions Before Implementation

**Files:**

- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_functions.py`
- Modify: `tests/test_workflow_lisp_macros.py`
- Modify: `tests/test_workflow_lisp_procedures.py`

- [ ] **Step 1: Add a duplicate-helper source-integrity regression**

In `tests/test_workflow_lisp_lowering.py`, add a narrow test that parses `orchestrator/workflow_lisp/lowering.py` with `ast` and counts top-level function definitions named:

- `_origin_for_workflow`
- `_procedure_provenance_notes`
- `_definition_only_module`

Expected assertion: each count is exactly `1`.

- [ ] **Step 2: Add the private-workflow type-authority regression**

Use `tests/test_workflow_lisp_procedures.py` to lock the path that needs `VariantCaseTypeRef`. Preferred path: keep the existing metadata-not-name-heuristic private-workflow union-match test and extend it only enough to prove the lowering path completes and the generated private workflow mapping is inspected successfully when the generated workflow name is monkeypatched away from any name heuristic.

Expected failure before the fix: `NameError` or equivalent lowering failure caused by the missing `VariantCaseTypeRef` symbol.

- [ ] **Step 3: Add the fail-closed purity regression**

In `tests/test_workflow_lisp_functions.py`, add a focused unit test against `_find_purity_violation(...)` or `_validate_pure_function_expr(...)` using a tiny test-local `ExprNode`-like dataclass that is not covered by any existing `isinstance(...)` branch.

Expected assertion after the fix:

- the helper purity path raises `LispFrontendCompileError`;
- the first diagnostic code is `pure_function_has_effect`;
- the message mentions an unsupported or unknown helper expression container.

- [ ] **Step 4: Add malformed-expanded-shape macro regressions**

In `tests/test_workflow_lisp_macros.py`, add two focused tests where a same-file macro expands to malformed shapes headed by `match` and `defworkflow` respectively.

Required assertions:

- compilation raises `LispFrontendCompileError`, not `IndexError`, `TypeError`, or another uncaught Python exception;
- the diagnostic comes from owned validation/elaboration, with expansion provenance still attached when applicable.

Keep these tests narrow: they are proving the hygiene guard and provenance preservation, not introducing a larger macro feature surface.

- [ ] **Step 5: Collect the touched tests before implementation**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_functions.py tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_procedures.py -q
```

Expected: the new tests collect successfully.

- [ ] **Step 6: Run the narrow failing selectors**

Run only the new or directly affected tests first so the failures prove the hazards before implementation. Prefer selectors scoped to the new tests plus the existing private-workflow regression.

Expected before code changes:

- duplicate-helper count test fails on count `2`;
- private-workflow regression fails on missing `VariantCaseTypeRef`;
- purity fail-closed regression fails because the unknown node currently returns `None`;
- malformed expanded `match` / `defworkflow` regressions fail with an uncaught Python exception or with the wrong failure mode.

- [ ] **Step 7: Commit the failing-test baseline**

```bash
git add tests/test_workflow_lisp_functions.py tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_procedures.py
git commit -m "test: lock workflow lisp preflight hazard regressions"
```

## Task 2: Remove Shadowed Lowering Helpers And Repair The Missing Import

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_procedures.py`

- [ ] **Step 1: Delete the earlier shadowed helper bodies**

In `orchestrator/workflow_lisp/lowering.py`, remove the earlier duplicate definitions of:

- `_origin_for_workflow`
- `_procedure_provenance_notes`
- `_definition_only_module`

Keep the later bodies exactly as the semantic baseline unless a failing regression proves a mechanical correction is required.

- [ ] **Step 2: Repair the lowering import**

Import `VariantCaseTypeRef` from `orchestrator.workflow_lisp.type_env` beside the existing `RecordTypeRef` and `WorkflowRefTypeRef` imports. Do not change the surrounding type-analysis branching beyond what is needed to use the existing shared type authority.

- [ ] **Step 3: Re-run only the lowering/procedures regressions**

Run the duplicate-helper regression and the private-workflow regression selectors.

Expected: both now pass, and no new lowering-source-map or private-workflow behavior changes are introduced.

- [ ] **Step 4: Commit the lowering hazard cleanup**

```bash
git add orchestrator/workflow_lisp/lowering.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_procedures.py
git commit -m "fix: remove shadowed lowering helpers"
```

## Task 3: Make Helper Purity Fail Closed

**Files:**

- Modify: `orchestrator/workflow_lisp/functions.py`
- Modify: `tests/test_workflow_lisp_functions.py`

- [ ] **Step 1: Change the unknown-expression default**

Update `_find_purity_violation(...)` so the final fallback returns a non-`None` violation for unknown expression containers instead of `None`.

Implementation constraints:

- do not weaken any existing explicit pure cases;
- do not introduce a new runtime surface;
- keep the result flowing through `_validate_pure_function_expr(...)` so the outward diagnostic code remains `pure_function_has_effect`.

- [ ] **Step 2: Keep the violation message actionable**

Ensure the reported violation text includes enough detail to identify that an unsupported helper expression container was encountered. A class-name-based message is acceptable if it stays deterministic.

- [ ] **Step 3: Re-run the helper purity regressions**

Run the new fail-closed test plus the existing helper purity/cycle/normalization tests in `tests/test_workflow_lisp_functions.py`.

Expected: the new test passes and no existing helper contract regresses.

- [ ] **Step 4: Commit the purity fix**

```bash
git add orchestrator/workflow_lisp/functions.py tests/test_workflow_lisp_functions.py
git commit -m "fix: fail closed on unknown helper expressions"
```

## Task 4: Guard Macro Hygiene Shape Assumptions

**Files:**

- Modify: `orchestrator/workflow_lisp/macros.py`
- Modify: `tests/test_workflow_lisp_macros.py`

- [ ] **Step 1: Guard `_hygienic_match(...)`**

Add minimum-shape checks before indexing `datum.items[1]` or slicing match arms. If the shape is malformed, fall back to safe recursive hygiene over children where possible and leave the malformed structure available for downstream validators.

- [ ] **Step 2: Guard `_hygienic_defworkflow(...)`**

Add minimum-shape checks before indexing the params node or body slot. If the shape is malformed, preserve the syntax object and expansion provenance and return through the same safe fallback strategy rather than raising an uncaught Python error.

- [ ] **Step 3: Keep provenance intact**

Do not strip `span`, `form_path`, or `expansion_stack` metadata while adding the guards. The resulting downstream diagnostic must still be able to point at the macro-produced form and its expansion history.

- [ ] **Step 4: Re-run the malformed-expanded-shape macro regressions**

Run the new malformed `match` and malformed `defworkflow` tests plus the existing macro hidden-effect/reserved-name coverage in `tests/test_workflow_lisp_macros.py`.

Expected: the new tests now fail through owned diagnostics instead of uncaught Python exceptions, and existing macro constraints still pass.

- [ ] **Step 5: Commit the macro hygiene hardening**

```bash
git add orchestrator/workflow_lisp/macros.py tests/test_workflow_lisp_macros.py
git commit -m "fix: guard workflow lisp macro hygiene shapes"
```

## Task 5: Final Verification And Handoff

**Files:**

- Verify only; no planned code changes

- [ ] **Step 1: Run the exact ordered verification contract**

Run these commands from the repo root in this exact order:

```bash
python -m compileall orchestrator/workflow_lisp
python -m pytest --collect-only tests/test_workflow_lisp_functions.py tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_procedures.py -q
python -m pytest tests/test_workflow_lisp_functions.py tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_procedures.py -q
git diff --check
```

Expected:

- `compileall` succeeds;
- collect-only succeeds and includes the touched tests;
- the four-module pytest run passes;
- `git diff --check` reports no whitespace or conflict-marker issues.

- [ ] **Step 2: Record verification evidence**

Capture the exact command outputs in the implementation notes or handoff summary. Do not claim success from inspection alone.

- [ ] **Step 3: Confirm scope discipline before merge or handoff**

Before closing the task, verify that the patch does not include:

- shared traversal extraction;
- lowering package splitting;
- review-loop special-case removal;
- imported `.orc` expansion or form-registry work;
- runtime/spec behavior changes outside the selected hazards.

- [ ] **Step 4: Final commit**

```bash
git add orchestrator/workflow_lisp/functions.py orchestrator/workflow_lisp/lowering.py orchestrator/workflow_lisp/macros.py tests/test_workflow_lisp_functions.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_procedures.py
git commit -m "fix: harden workflow lisp preflight hazards"
```
