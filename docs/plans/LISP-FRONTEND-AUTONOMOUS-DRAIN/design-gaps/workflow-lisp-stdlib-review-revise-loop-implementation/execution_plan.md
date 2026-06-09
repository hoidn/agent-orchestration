# Workflow Lisp Stdlib Review/Revise Loop Stage 10 Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` to execute this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the selected Stage 10 work item by converging the already-landed ordinary `std/phase.orc` review-loop route on the target design's final ownership and verification requirements: macro-only public stdlib ownership, compile-time `ProcRef` hooks, strict review-report/findings authority, no bridge-era public operands, and no lingering promoted-path dependence on literal review-loop compiler branches.

**Architecture:** The current checkout already lands the core route that the target design wanted to unlock: `review-revise-loop` is a `FormKind.STDLIB_EXTENSION`, `StdlibSpecializationExpr` and `ReviewReviseLoopExpr` are gone, `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` owns `ReviewDecision` / `ReviewFindings` / `ReviewLoopResult`, and focused tests already prove seed-role split, imported generic consumer composition, and resume-safe loop checkpoints. This plan therefore treats Stage 10 as a convergence and cleanup slice, not a greenfield implementation: first re-prove the prerequisite owner slices in the current checkout, then encode the remaining contract gaps as tests, then remove or explicitly quarantine the few remaining literal-name review-loop helpers in compiler, typecheck, and lowering code without reopening prerequisite work or widening into shared runtime changes.

**Tech Stack:** Workflow Lisp `.orc` stdlib/modules, Python frontend modules under `orchestrator/workflow_lisp/`, shared runtime/validation reuse, `pytest`

---

## Fixed Inputs

Treat these as the implementation authority for this plan:

- `docs/index.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/8/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

Additional governing references selected via `docs/index.md` because the work-item context depends on them:

- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/design/workflow_lisp_refactor_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-loop-recur-on-exhausted-projection/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parametric-loop-state-authoring/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-generic-loop-state-consumer-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-review-loop-report-findings-path-split/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-review-loop-resume-checkpoint-identity/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parametric-defproc-specialization-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-structural-parametric-constraints/implementation_architecture.md`

## Current Checkout Facts

These facts were verified before writing this plan and should guide execution:

- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` is empty, so no later ledger event supersedes this selected work item.
- `docs/steering.md` is empty in this checkout and does not widen scope.
- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` already owns:
  - `ReviewReportPath`
  - `ReviewFindingsJsonPath`
  - `ReviewFindings`
  - `ReviewDecision`
  - `ReviewLoopResult`
  - `review-revise-loop-proc`
  - `review-revise-loop`
- `review-revise-loop` already compiles through ordinary imported stdlib expansion plus `loop/recur`, `match`, `command-result`, and provider-result composition; bridge expression nodes are already absent.
- `orchestrator/workflow_lisp/form_registry.py` already classifies `review-revise-loop` as `FormKind.STDLIB_EXTENSION` with `owner_module="stdlib_modules/std/phase.orc"` and `macro_bindable=True`.
- Focused prerequisite proofs already exist in tests:
  - authored `loop/recur :on-exhausted`
  - authored loop-state carriage
  - imported generic loop-state consumer proof
  - review-report/findings seed split
  - imported review-loop resume checkpoint identity
- The main residual Stage 10 tension is not missing stdlib authoring. It is the remaining literal-name review-loop helpers in compiler/lowering code, especially:
  - `orchestrator/workflow_lisp/compiler.py::_workflow_contains_review_revise_loop`
  - `orchestrator/workflow_lisp/typecheck_effects.py` fallback binding for literal `validate_review_findings_v1`
  - review-loop-specific output helper functions in `orchestrator/workflow_lisp/lowering/phase_stdlib.py`
  - the still-public export of `review-revise-loop-proc`, if that turns out not to be required for macro expansion

## Hard Scope Limits

Implement only the bounded Stage 10 convergence work described by the target design and the selected work item:

- preserve ordinary `std/phase.orc` ownership of the review/revise loop surface;
- preserve the exact stdlib-owned protocol:
  - `ReviewReportPath`
  - `ReviewFindingsJsonPath`
  - `ReviewFindings`
  - `ReviewDecision`
  - `ReviewLoopResult`
- preserve compile-time-only `ProcRef` review/fix hooks;
- preserve caller-side terminal projection and evidence authority;
- remove or explicitly quarantine remaining compiler/typecheck/lowering literal-name dependencies on review-loop semantics;
- add only the fixtures and tests needed to prove the final Stage 10 contract.

Do not widen this work item into:

- Track A imported `.orc` expansion work;
- new parametric-specialization or structural-constraint work;
- new loop-state or `:on-exhausted` substrate work;
- new shared runtime behavior under `orchestrator/workflow/`;
- new command adapters, report parsing, hidden Python/shell glue, or pointer-as-authority behavior;
- broad refactors unrelated to the selected review-loop route.

Stop immediately and reopen the owner slice instead of patching around it here if any prerequisite proof fails in the current checkout.

## File Map

Primary implementation files:

- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/typecheck_effects.py`
- `orchestrator/workflow_lisp/lowering/phase_stdlib.py`
- `orchestrator/workflow_lisp/stdlib_contracts.py`

Primary verification and fixture files:

- `tests/fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc`
- `tests/fixtures/workflow_lisp/invalid/review_loop_findings_contract_invalid.orc`
- `tests/fixtures/workflow_lisp/invalid/review_loop_result_contract_invalid.orc`
- `tests/fixtures/workflow_lisp/invalid/review_loop_legacy_bridge_operands_invalid.orc`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_key_migrations.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_expressions.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_macros.py`
- `tests/test_workflow_lisp_modules.py`

Inspect only unless a failing test proves they must change:

- `orchestrator/workflow_lisp/typecheck_dispatch.py`
- `orchestrator/workflow_lisp/procedure_typecheck.py`
- `orchestrator/workflow_lisp/procedure_specialization.py`
- `orchestrator/workflow_lisp/loop_state.py`
- `orchestrator/workflow_lisp/loops.py`
- `orchestrator/workflow_lisp/source_map.py`
- `orchestrator/workflow_lisp/form_registry.py`

Do not modify unless this plan is materially underspecified:

- shared runtime modules under `orchestrator/workflow/`
- `specs/`
- unrelated stdlib forms

### Task 1: Re-Prove Stage 10 Prerequisite Gates Before Editing

**Files:**

- Verify only: `tests/test_workflow_lisp_procedures.py`
- Verify only: `tests/test_workflow_lisp_phase_stdlib.py`
- Verify only: `tests/test_workflow_lisp_build_artifacts.py`
- Verify only: `tests/test_workflow_lisp_key_migrations.py`

- [ ] **Step 1: Run the narrow prerequisite selectors**

Run:

```bash
pytest tests/test_workflow_lisp_procedures.py::test_compile_stage3_imported_generic_loop_state_consumer_specializes_without_runtime_leaks -v
pytest tests/test_workflow_lisp_procedures.py::test_compile_stage3_imported_generic_loop_state_consumer_preserves_custom_schema_version_on_exhausted_state_projection -v
pytest tests/test_workflow_lisp_phase_stdlib.py::test_authored_loop_state_review_findings_keeps_strict_relpath_contracts -v
pytest tests/test_workflow_lisp_phase_stdlib.py::test_review_loop_direct_route_populates_loop_recur_on_exhausted_result_expr -v
pytest tests/test_workflow_lisp_key_migrations.py::test_review_loop_parity_fixture_compiles_to_resume_safe_repeat_until_via_imported_stdlib_route -v
pytest tests/test_workflow_lisp_key_migrations.py::test_review_loop_imported_stdlib_route_resumes_after_revise_checkpoint -v
```

Expected:

- all six tests pass;
- if any fail, stop this work item and reopen the prerequisite owner slice named by the failing test area.

- [ ] **Step 2: Run the current Stage 10 smoke selectors**

Run:

```bash
pytest tests/test_workflow_lisp_phase_stdlib.py::test_review_loop_compiles_without_bridge_controls -v
pytest tests/test_workflow_lisp_phase_stdlib.py::test_review_loop_valid_fixture_preserves_review_report_and_findings_roots -v
pytest tests/test_workflow_lisp_phase_stdlib.py::test_review_revise_loop_review_bundle_path_is_generated_write_root -v
pytest tests/test_workflow_lisp_build_artifacts.py::test_review_loop_bundle_preserves_distinct_review_report_and_findings_seed_paths -v
```

Expected:

- all four tests pass;
- their output becomes the baseline evidence for the rest of this task.

### Task 2: Encode The Remaining Stage 10 Contract As Failing Tests

**Files:**

- Modify: `tests/fixtures/workflow_lisp/invalid/review_loop_legacy_bridge_operands_invalid.orc`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_key_migrations.py`
- Modify: `tests/test_workflow_lisp_modules.py`
- Modify: `tests/test_workflow_lisp_expressions.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_macros.py`

- [ ] **Step 1: Reuse the existing explicitly legacy fixture for bridge-era public operands**

Update `tests/fixtures/workflow_lisp/invalid/review_loop_legacy_bridge_operands_invalid.orc` so the bridge-era operand surface stays explicitly marked legacy while still calling `review-revise-loop` with one or more forbidden operands:

- `:review-provider`
- `:fix-provider`
- `:review-prompt`
- `:fix-prompt`
- `:returns`

Expected failure mode:

- elaboration or typecheck rejects the public surface;
- no fallback path silently accepts bridge-era operands.

- [ ] **Step 2: Add failing owner tests for the final public contract**

Add targeted tests that prove:

- builtin `std/phase` still exposes `review-revise-loop` as the public macro surface;
- legacy bridge operands are rejected;
- review-loop output authority still keeps review reports under `artifacts/review` and findings under `artifacts/work`;
- resume checkpoint identity still uses the same loop frame key after any cleanup;
- no test relies on literal prompt text.

- [ ] **Step 3: Add failing regression tests for residual compiler/lowering ownership**

Add one source-level or behavioral regression per owner module proving:

- `compiler.py` no longer needs literal-name syntax/procedure scanning to decide whether the validator binding is required;
- `typecheck_effects.py` no longer relies on a review-loop-only fallback for literal `validate_review_findings_v1`, or the retained fallback is explicitly documented as the accepted quarantine boundary for this slice;
- `lowering/phase_stdlib.py` does not reintroduce a hidden bridge path or review-loop-only output semantics beyond the accepted Stage 10 quarantine boundary;
- if `review-revise-loop-proc` remains exported, the test must explain why the export is intentionally retained; otherwise test for macro-only public exposure.

- [ ] **Step 4: If any test file is added or renamed, run collection**

Run:

```bash
pytest --collect-only tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_key_migrations.py tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_lowering.py
```

Expected:

- the new tests are discoverable;
- no accidental duplicate or shadowed test names.

### Task 3: Remove Or Quarantine Residual Literal-Name Review-Loop Compiler, Typecheck, And Lowering Ownership

**Files:**

- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/typecheck_effects.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_stdlib.py`
- Modify: `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- Modify: `orchestrator/workflow_lisp/stdlib_contracts.py`

- [ ] **Step 1: Replace review-loop literal-name detection in `compiler.py`**

Implement the narrowest change that removes semantic dependence on:

- `review_loop_public_surface` feature-tag scanning for behavior;
- `.../review-revise-loop-proc` suffix scanning.

Preferred outcome:

- validator binding registration is driven by an ordinary owner surface such as actual command-boundary demand, typed lowered usage, or explicit stdlib contract metadata;
- the compiler no longer needs a review-loop-specific tree walk.

- [ ] **Step 2: Remove or explicitly quarantine the literal `validate_review_findings_v1` typecheck fallback**

In `orchestrator/workflow_lisp/typecheck_effects.py`, either:

- route the binding through ordinary certified-adapter / command-boundary metadata so review-loop presence is no longer inferred from a literal command name; or
- keep the fallback only if it is the narrowest accepted Stage 10 quarantine, add a short comment naming that boundary, and cover it with a dedicated regression test.

Do not broaden this into new adapter design or runtime behavior.

- [ ] **Step 3: Reduce review-loop-specific lowering helpers to the accepted minimum**

Keep only the logic that is still genuinely Stage 10-specific:

- result-union normalization that is still local to this stdlib form;
- source-map or contract plumbing that cannot yet be shared without widening scope.

Remove or refactor anything that still behaves like a hidden bridge-era branch.

- [ ] **Step 4: Tighten the public stdlib surface if the macro no longer needs a public helper proc**

Evaluate whether `review-revise-loop-proc` must remain exported from `std/phase.orc`.

If not required:

- stop exporting it;
- update builtin-import tests accordingly.

If it must remain exported:

- keep it;
- add a small code comment and a test that records the reason so future cleanup has a clear follow-up target.

- [ ] **Step 5: Preserve the already-landed authority boundaries**

Do not regress any of these while cleaning up:

- `ReviewFindings.items_path` stays `ReviewFindingsJsonPath` under `artifacts/work`;
- review reports stay under `artifacts/review`;
- generated seed roles remain distinct;
- `fix` continues to receive validated findings from the immediately preceding `REVISE` path;
- runtime-visible artifacts remain free of `ProcRef`, provider refs, prompt refs, and type parameters.

### Task 4: Align Fixtures And Runtime Proofs With The Final Stage 10 Surface

**Files:**

- Modify: `tests/fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc`
- Modify: `tests/fixtures/workflow_lisp/invalid/review_loop_findings_contract_invalid.orc`
- Modify: `tests/fixtures/workflow_lisp/invalid/review_loop_result_contract_invalid.orc`
- Modify: `tests/fixtures/workflow_lisp/invalid/review_loop_legacy_bridge_operands_invalid.orc`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_key_migrations.py`

- [ ] **Step 1: Keep the valid fixture on the final public route only**

The valid review-loop fixture must use only:

- `with-phase`
- `review-revise-loop`
- `:ctx`
- `:completed`
- `:inputs`
- `:review`
- `:fix`
- `:max`

and compile-time `proc-ref` hooks.

- [ ] **Step 2: Keep negative fixtures focused and non-overlapping**

Use separate fixtures/tests for:

- invalid findings-path contract;
- invalid review-decision/result-shape contract;
- forbidden legacy public operands.

- [ ] **Step 3: Re-run the runtime proof after cleanup**

The runtime resume selector in `tests/test_workflow_lisp_key_migrations.py` is the required integration check for this slice because the work touches frontend lowering and reusable review-loop mechanics.

Expected:

- the imported stdlib route still resumes after a forced `REVISE` interruption;
- the persisted loop frame key stays stable;
- evidence roots remain unchanged.

### Task 5: Final Verification And Evidence Capture

**Files:**

- Verify only: `tests/test_workflow_lisp_phase_stdlib.py`
- Verify only: `tests/test_workflow_lisp_build_artifacts.py`
- Verify only: `tests/test_workflow_lisp_key_migrations.py`
- Verify only: `tests/test_workflow_lisp_procedures.py`
- Verify only: `tests/test_workflow_lisp_modules.py`
- Verify only: `tests/test_workflow_lisp_expressions.py`
- Verify only: `tests/test_workflow_lisp_lowering.py`
- Verify only: `tests/test_workflow_lisp_macros.py`

- [ ] **Step 1: Run the exact touched-test selectors first**

Run the new or modified test selectors individually with `-v`.

Expected:

- each targeted behavior passes in isolation before broader module runs.

- [ ] **Step 2: Run the owner-module suites that cover the selected route**

Run:

```bash
pytest tests/test_workflow_lisp_phase_stdlib.py -k "review_loop or authored_loop_state_review_findings" -v
pytest tests/test_workflow_lisp_build_artifacts.py -k "review_loop or review_findings" -v
pytest tests/test_workflow_lisp_key_migrations.py -k "review_loop" -v
pytest tests/test_workflow_lisp_procedures.py -k "imported_generic_loop_state_consumer" -v
pytest tests/test_workflow_lisp_modules.py -k "review_loop" -v
pytest tests/test_workflow_lisp_expressions.py -k "review_revise_loop" -v
pytest tests/test_workflow_lisp_lowering.py -k "review_loop or stdlib_contract_inventory" -v
pytest tests/test_workflow_lisp_macros.py -k "review_revise_loop" -v
```

Expected:

- all selected suites pass;
- no bridge-era public route or literal-name compiler dependency remains.

- [ ] **Step 3: Record verification evidence in the work summary**

Capture at minimum:

- which prerequisite selectors were re-run;
- which Stage 10 selectors were added or changed;
- whether `review-revise-loop-proc` remained exported or was de-exported;
- whether `typecheck_effects.py` still retains any documented quarantine for `validate_review_findings_v1`;
- the final runtime resume proof result;
- any intentional quarantine that remains and why it was kept in-scope.

## Completion Criteria

This plan is complete when all of the following are true:

- prerequisite proofs for Sections 12.1, 12.2, and 12.3 still pass in the current checkout;
- `review-revise-loop` remains owned by ordinary `std/phase.orc` code and the public surface is macro-first;
- bridge-era public operands are rejected;
- carried evidence authority and review-report/findings root separation remain intact;
- resume proof still passes after cleanup;
- no remaining review-loop compiler, typecheck, or lowering behavior depends on the removed promoted bridge path except any explicitly documented, narrowly justified quarantine.
