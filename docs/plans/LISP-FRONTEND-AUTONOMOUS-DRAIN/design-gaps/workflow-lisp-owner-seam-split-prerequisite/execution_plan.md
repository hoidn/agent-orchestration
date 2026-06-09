# Workflow Lisp Owner-Seam Split Prerequisite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` to execute this plan task-by-task. Do not create a git worktree; `AGENTS.md` forbids worktrees for this repo. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the bounded owner-seam prerequisite by making `procedure_typecheck.py`, `procedure_specialization.py`, and `lowering/procedures.py` the real owners of the selected procedure seams, while preserving current `.orc` behavior, diagnostics, source maps, shared-validation behavior, and runtime behavior.

**Architecture:** The checkout already contains the package-facade and owner-module scaffolding. Implementation should treat that scaffolding as the starting point, then finish the ownership move: keep `compiler.py`, `typecheck.py`, and `orchestrator.workflow_lisp.lowering` as compatibility/coordinator facades, move the remaining procedure-lowering and specialization-eligibility logic out of `lowering/core.py`, and tighten tests so future Track A or parametric work targets the owner modules instead of the public facades.

**Tech Stack:** Python 3, dataclasses, the existing `orchestrator.workflow_lisp` frontend pipeline, shared workflow validation/runtime integration in `orchestrator.workflow`, and pytest.

---

## Fixed Inputs

Treat these as authority for this slice:

- `docs/index.md`
- `docs/steering.md`
  - currently empty in this checkout; no local steering overrides the selected gap
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - especially sections `8.1`, `9.4`, and `24`
- `docs/design/workflow_lisp_refactor_architecture.md`
- `docs/plans/2026-06-02-workflow-lisp-low-hanging-refactor-plan.md`
- `docs/plans/2026-06-02-workflow-lisp-generic-orc-expansion-refactor.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-owner-seam-split-prerequisite/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/4/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`
  - currently `{"ledger_version":1,"events":[]}`; no later ledger event supersedes this prerequisite

## Current Checkout Starting Point

Implementation must start from the checkout that exists now, not from the older architecture snapshot:

- `orchestrator/workflow_lisp/lowering.py` is already gone; `orchestrator/workflow_lisp/lowering/` already exists.
- `orchestrator/workflow_lisp/procedure_specialization.py` already exists and already owns:
  - `procedure_catalog_with_specializations(...)`
  - `bound_proc_ref_request(...)`
  - `discover_proc_ref_specializations(...)`
- `orchestrator/workflow_lisp/procedure_typecheck.py` already exists and already owns:
  - `typecheck_procedure_definitions(...)`
  - `typecheck_procedure_call_expr(...)`
  - `typecheck_generated_procedure(...)`
- `orchestrator/workflow_lisp/lowering/procedures.py` already exists, but it is still mostly a thin wrapper layer.
- `compiler.py` no longer imports `_specialize_typed_procedure(...)` from lowering; that part of the seam split is already in place.
- `typecheck.py` already delegates `ProcedureCallExpr` and generated-procedure typing through `procedure_typecheck.py`.
- The remaining owner-seam debt is concentrated in lowering and specialization eligibility:
  - `lowering/core.py` still defines `_resolve_procedure_lowering(...)`
  - `lowering/core.py` still defines `_lower_procedure_call_expr(...)`
  - `lowering/core.py` still defines `_private_workflow_from_procedure(...)`
  - `lowering/core.py` still defines `_procedure_provenance_notes(...)`
  - `lowering/core.py` still defines `_procedure_private_call_site_analysis(...)`
  - `lowering/core.py` still defines `_procedure_private_boundary_valid(...)`
  - `lowering/core.py` still defines `_procedure_private_body_valid(...)`
  - `procedure_specialization.py` still imports the private-workflow eligibility helpers from `lowering.core`
  - `tests/test_workflow_lisp_lowering.py::test_lowering_facade_exports_current_test_surface` currently imports `orchestrator.workflow_lisp.lowering.core` directly instead of validating the facade import path

Line-count facts from this checkout:

- `orchestrator/workflow_lisp/compiler.py`: 3,064 lines
- `orchestrator/workflow_lisp/typecheck.py`: 5,855 lines
- `orchestrator/workflow_lisp/lowering/core.py`: 10,980 lines
- `orchestrator/workflow_lisp/procedure_specialization.py`: 430 lines
- `orchestrator/workflow_lisp/procedure_typecheck.py`: 346 lines
- `orchestrator/workflow_lisp/lowering/procedures.py`: 253 lines

## Scope Limits

In scope:

- finishing the already-started owner-seam move for:
  - procedure-call typechecking integration
  - specialization discovery/materialization integration
  - procedure-call lowering, provenance, and lowering-boundary runtime-erasure checks
- moving the real procedure-lowering and private-workflow-eligibility implementations out of `lowering/core.py`
- leaving `compiler.py`, `typecheck.py`, and `orchestrator.workflow_lisp.lowering` as compatibility/coordinator surfaces only
- tightening focused owner-boundary tests so the seam cannot drift back into the public facades
- updating `orchestrator/workflow_lisp/README.md` so the code map matches the landed ownership

Out of scope:

- Track A form-registry work or imported `.orc` expansion
- review-loop de-specialization
- new parametric `defproc`, structural constraints, or `loop/recur` exhaustion behavior
- unrelated cleanup of other large modules
- shared runtime, shared validation, Semantic IR, Executable IR, or Core Workflow AST redesign
- new command adapters or policy changes beyond preserving current command-boundary guarantees

## Files And Responsibilities

Modify:

- `orchestrator/workflow_lisp/procedure_specialization.py`
- `orchestrator/workflow_lisp/procedure_typecheck.py`
  - only if a small helper or context adjustment is required to keep ownership coherent
- `orchestrator/workflow_lisp/lowering/__init__.py`
- `orchestrator/workflow_lisp/lowering/core.py`
- `orchestrator/workflow_lisp/lowering/procedures.py`
- `orchestrator/workflow_lisp/compiler.py`
  - only for compatibility imports/wrappers if the moved lowering helpers change import shape
- `orchestrator/workflow_lisp/typecheck.py`
  - only for compatibility glue if required by the extracted owner surface
- `orchestrator/workflow_lisp/README.md`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_workflow_refs.py`
- `tests/test_workflow_lisp_phase_stdlib.py`

Avoid widening into unrelated files unless an import cycle forces a purely mechanical shim.

## Acceptance Target

This prerequisite is complete only when all of the following are true:

- the exact owner file paths remain:
  - `orchestrator/workflow_lisp/procedure_typecheck.py`
  - `orchestrator/workflow_lisp/procedure_specialization.py`
  - `orchestrator/workflow_lisp/lowering/procedures.py`
- `orchestrator.workflow_lisp.lowering` remains the stable public import facade
- `lowering/core.py` no longer contains the real implementations for the selected procedure-lowering seam; it may import or delegate, but it is no longer the only owner
- `procedure_specialization.py` no longer imports private-workflow eligibility helpers from `lowering.core`
- procedure-call typing, specialization, provenance notes, generated private workflows, workflow-ref specialization, and runtime-erasure behavior remain unchanged on the focused regressions below
- touched owner modules stay below the 2,000-line cap after the move

## Task 1: Tighten Owner-Boundary Tests Around The Current Checkout

**Files:**

- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_workflow_refs.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] **Step 1: Rewrite the facade test to validate the facade, not `lowering.core`**

Change `tests/test_workflow_lisp_lowering.py::test_lowering_facade_exports_current_test_surface` so it imports `orchestrator.workflow_lisp.lowering` and asserts the facade exports:

- `_resolve_procedure_lowering`
- `_managed_write_root_bindings`
- `_managed_write_root_requirements_for_callable`
- `_observed_statement_families`
- `_workflow_extern_requirements`
- `lower_workflow_definitions`
- `validate_lowered_workflows`

Do not make tests import `lowering.core` directly when they are validating the public surface.

- [ ] **Step 2: Add source-structure guards for the residual seam debt**

Add narrow architecture tests that currently fail:

- in `tests/test_workflow_lisp_lowering.py`
  - assert `lowering/core.py` no longer defines:
    - `_resolve_procedure_lowering`
    - `_lower_procedure_call_expr`
    - `_private_workflow_from_procedure`
    - `_procedure_provenance_notes`
  - keep the existing duplicate-helper count guard, but aim it at the final owner files after the move
- in `tests/test_workflow_lisp_procedures.py`
  - assert `procedure_specialization.py` does not import `_procedure_private_boundary_valid` or `_procedure_private_body_valid` from `lowering.core`
  - keep the existing compiler import guard:
    `test_compiler_owner_split_stops_importing_procedure_specialization_from_lowering`

- [ ] **Step 3: Add one focused runtime-erasure negative test**

Add a direct unit test in `tests/test_workflow_lisp_lowering.py` that imports `_assert_runtime_erasure` from `orchestrator.workflow_lisp.lowering.procedures` and proves it raises `proc_runtime_erasure_failed` when passed a compile-time-only value such as `ResolvedProcRefValue`.

This test is the seam guard for the fail-closed runtime boundary; it does not need to force a full workflow compile.

- [ ] **Step 4: Preserve the existing focused behavior guards**

Keep these tests as the non-negotiable behavioral coverage for the owner split:

- `tests/test_workflow_lisp_procedures.py::test_stage3_discovery_walks_nested_proc_ref_specializations_in_owner_forms`
- `tests/test_workflow_lisp_procedures.py::test_stage3_materializes_proc_ref_specializations_before_lowering_and_preserves_effects`
- `tests/test_workflow_lisp_procedures.py::test_higher_order_procedure_specializations_reuse_private_workflow_lowering`
- `tests/test_workflow_lisp_workflow_refs.py::test_workflow_ref_specialization_through_owner_seam_compiles_and_validates`
- `tests/test_workflow_lisp_phase_stdlib.py::test_review_loop_specializes_to_ordinary_typed_forms`
- `tests/test_workflow_lisp_phase_stdlib.py::test_review_loop_validator_binding_registers_only_when_review_loop_present`

Do not replace these with full-workflow snapshots.

- [ ] **Step 5: Collect and run the new failing boundary slice**

Run:

```bash
pytest --collect-only \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_workflow_refs.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  -q
```

Then run the narrow failing slice:

```bash
pytest \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_procedures.py \
  -k "facade or owner_split or runtime_erasure" \
  -q
```

Expected before implementation: the new owner-boundary tests fail because `lowering/core.py` still owns the selected implementations and `procedure_specialization.py` still imports eligibility helpers from core.

- [ ] **Step 6: Commit**

```bash
git add \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_workflow_refs.py \
  tests/test_workflow_lisp_phase_stdlib.py
git commit -m "test: lock workflow lisp owner seam boundaries"
```

## Task 2: Move Private-Workflow Eligibility Out Of `lowering/core.py`

**Files:**

- Modify: `orchestrator/workflow_lisp/procedure_specialization.py`
- Modify: `orchestrator/workflow_lisp/lowering/procedures.py`
- Modify: `orchestrator/workflow_lisp/lowering/core.py`
- Modify: `tests/test_workflow_lisp_procedures.py`

- [ ] **Step 1: Make specialization own its private-workflow eligibility logic**

Move the helpers used by `specialize_typed_procedure(...)` out of `lowering/core.py` and into the owner seam.

The final shape should be:

- `procedure_specialization.py`
  - owns the boundary/body eligibility checks needed while materializing one specialized procedure
  - does not import those checks from `lowering.core`
- `lowering/procedures.py`
  - consumes the same eligibility surface when resolving lowering modes for typed procedures

Do not leave `specialize_typed_procedure(...)` depending on `lowering.core` private helpers after this step.

- [ ] **Step 2: Keep call-site-count analysis with the lowering owner**

Move `_procedure_private_call_site_analysis(...)` out of `lowering/core.py` and into `lowering/procedures.py`, because it is part of resolving the lowering strategy for typed procedures rather than compile coordination.

Keep `_resolve_procedure_lowering(...)` in the lowering owner module and have it call the moved analysis directly there.

- [ ] **Step 3: Leave only compatibility imports in `lowering/core.py`**

After the move:

- `lowering/core.py` may import procedure-specific helpers from `lowering/procedures.py`
- `lowering/core.py` must stop defining the real eligibility/planning helpers itself
- `procedure_specialization.py` must not reach back into `lowering/core.py` for this seam

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest \
  tests/test_workflow_lisp_procedures.py::test_compiler_owner_split_stops_importing_procedure_specialization_from_lowering \
  tests/test_workflow_lisp_procedures.py::test_stage3_discovery_walks_nested_proc_ref_specializations_in_owner_forms \
  tests/test_workflow_lisp_workflow_refs.py::test_workflow_ref_specialization_through_owner_seam_compiles_and_validates \
  -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add \
  orchestrator/workflow_lisp/procedure_specialization.py \
  orchestrator/workflow_lisp/lowering/procedures.py \
  orchestrator/workflow_lisp/lowering/core.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_workflow_refs.py
git commit -m "refactor: move workflow lisp specialization eligibility to owner seams"
```

## Task 3: Make `lowering/procedures.py` The Real Procedure-Lowering Owner

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering/procedures.py`
- Modify: `orchestrator/workflow_lisp/lowering/core.py`
- Modify: `orchestrator/workflow_lisp/lowering/__init__.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] **Step 1: Move the real procedure-lowering bodies into `lowering/procedures.py`**

Make `lowering/procedures.py` own the actual implementations of:

- `_resolve_procedure_lowering(...)`
- `_lower_procedure_call_expr(...)`
- `_private_workflow_from_procedure(...)`
- `_procedure_provenance_notes(...)`

`lowering/procedures.py` may still import generic helpers from `lowering.core` such as `_compile_error`, `_LoweringContext`, `_TerminalResult`, `_lower_expression`, `_render_call_binding_ref`, `_render_record_call_bindings`, `_managed_write_root_binding_step`, `_managed_write_root_requirements_for_callable`, `_record_step_origin`, `_resolve_inline_expr_value`, `_resolved_proc_ref_value`, `_resolved_workflow_ref_value`, `_flatten_boundary_leaf_paths`, and `_procedure_signature_local_type_bindings`.

The ownership rule is:

- generic lowering infrastructure may stay in `core.py`
- procedure-specific planning, provenance, and runtime-erasure logic must live in `procedures.py`

- [ ] **Step 2: Delete duplicate procedure implementations from `lowering/core.py`**

After the move, remove the old definitions from `lowering/core.py` instead of leaving dead duplicate bodies behind.

Update the procedure-call branch in `core.py` to import and call the owner helper from `lowering.procedures`.

Also update workflow-level provenance assembly in `_origin_for_workflow(...)` so it imports the owner `_procedure_provenance_notes(...)` instead of relying on a local duplicate.

- [ ] **Step 3: Keep the public lowering facade stable**

Ensure `orchestrator.workflow_lisp.lowering` still re-exports the test-visible and caller-visible surface after the move.

Do not force callers to import `lowering.core` or `lowering.procedures` directly.

- [ ] **Step 4: Run focused checks**

Run:

```bash
python -m compileall orchestrator/workflow_lisp
pytest \
  tests/test_workflow_lisp_lowering.py::test_lowering_facade_exports_current_test_surface \
  tests/test_workflow_lisp_lowering.py::test_lowering_facade_source_defines_preflight_helpers_exactly_once \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_procedures.py::test_higher_order_procedure_specializations_reuse_private_workflow_lowering \
  tests/test_workflow_lisp_phase_stdlib.py::test_review_loop_specializes_to_ordinary_typed_forms \
  tests/test_workflow_lisp_phase_stdlib.py::test_review_loop_validator_binding_registers_only_when_review_loop_present \
  -q
```

Expected: compileall passes; the focused lowering and procedure tests pass.

- [ ] **Step 5: Commit**

```bash
git add \
  orchestrator/workflow_lisp/lowering/__init__.py \
  orchestrator/workflow_lisp/lowering/core.py \
  orchestrator/workflow_lisp/lowering/procedures.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_phase_stdlib.py
git commit -m "refactor: finish workflow lisp procedure lowering ownership"
```

## Task 4: Update The Code Map And Record Final Verification

**Files:**

- Modify: `orchestrator/workflow_lisp/README.md`

- [ ] **Step 1: Update the README ownership map**

Refresh the Workflow Lisp code map so it matches the landed seam ownership:

- `procedure_specialization.py` owns specialization discovery/materialization and specialized lowering-mode eligibility
- `procedure_typecheck.py` owns procedure-call and generated-procedure typing
- `lowering/procedures.py` owns procedure lowering, provenance notes, and runtime-erasure checks
- `lowering/core.py` is the generic lowering coordinator, not the procedure owner

- [ ] **Step 2: Run the required acceptance slice**

Run the exact acceptance evidence for this gap:

```bash
pytest --collect-only \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_workflow_refs.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  -q

python -m compileall orchestrator/workflow_lisp

pytest \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_workflow_refs.py::test_workflow_ref_specialization_through_owner_seam_compiles_and_validates \
  tests/test_workflow_lisp_phase_stdlib.py::test_review_loop_specializes_to_ordinary_typed_forms \
  tests/test_workflow_lisp_phase_stdlib.py::test_review_loop_validator_binding_registers_only_when_review_loop_present \
  -q

git diff --check
```

Expected: all commands pass.

- [ ] **Step 3: Optional broader audit only if needed**

If you also run any broader suite over touched files and it fails, classify each failure explicitly as one of:

- selected-seam regression
- unrelated touched-surface failure
- pre-existing unrelated failure

Do not silently widen this gap into a broader repair tranche.

- [ ] **Step 4: Commit**

```bash
git add orchestrator/workflow_lisp/README.md
git commit -m "docs: record workflow lisp owner seam split"
```

## Final Handoff Checklist

- [ ] `lowering/core.py` no longer contains the real procedure-lowering ownership bodies listed above
- [ ] `procedure_specialization.py` no longer imports private-workflow eligibility helpers from `lowering.core`
- [ ] `orchestrator.workflow_lisp.lowering` stays importable as the stable facade
- [ ] focused behavior tests for ProcRef specialization, workflow-ref forwarding, review-loop generated helpers, provenance notes, and runtime-erasure all pass
- [ ] touched owner modules remain below 2,000 lines
- [ ] unrelated dirty-worktree changes were not reverted
