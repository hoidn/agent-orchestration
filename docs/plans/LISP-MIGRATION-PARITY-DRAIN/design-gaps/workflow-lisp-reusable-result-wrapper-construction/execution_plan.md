# Workflow Lisp Reusable-Result Wrapper Construction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one ordinary Workflow Lisp authored surface for constructing declared union variants so reusable wrapper workflows can return authored unions and drive `resume-or-start :valid-when (APPROVED)` without compiler-family special casing or compiler-generated-only union constructors.

**Architecture:** Keep this slice entirely inside the existing Workflow Lisp frontend surface. Parse one explicit authored constructor form, elaborate it directly to the existing `UnionVariantExpr`, reuse the current union typecheck and lowering substrate, and prove the capability with a focused wrapper-level `resume-or-start` fixture rather than a family rewrite. Runtime semantics, reusable-state adapters, entrypoint context bootstrap, and YAML/runtime contracts stay unchanged.

**Tech Stack:** Python 3, Workflow Lisp frontend parser/typecheck/lowering, typed loaded bundles, `pytest`

---

## Fixed Inputs

Treat these as implementation authority:

- `docs/index.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-reusable-result-wrapper-construction/implementation_architecture.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/steering.md`
- `specs/dsl.md`
- `specs/state.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/0/design-gap-architect/work_item_context.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/0/design-gap-architect/check_commands.json`

Current checkout facts that must not be rediscovered during implementation:

- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json` is empty, so no later ledger event supersedes this slice.
- `docs/steering.md` is empty in this checkout and does not widen scope.
- `orchestrator/workflow_lisp/expressions.py` already exposes authored `record` construction, but ordinary expression elaboration does not expose any authored union-construction form.
- `orchestrator/workflow_lisp/expressions.py` still documents `UnionVariantExpr` as compiler-generated-only even though `orchestrator/workflow_lisp/typecheck.py` and `orchestrator/workflow_lisp/lowering.py` already accept and lower that node.
- `orchestrator/workflow_lisp/functions.py` and `orchestrator/workflow_lisp/compiler.py` already recurse through `UnionVariantExpr` like other pure aggregate nodes, so authored reuse should stay inside the existing purity/proc-ref traversal model.
- `tests/fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start.orc` and `tests/test_workflow_lisp_phase_stdlib.py::test_resume_or_start_supports_union_start_workflow_call` already prove `resume-or-start` accepts union-typed start arms, but the wrapper surface remains record-only after `match`.
- `tests/test_workflow_lisp_key_migrations.py::test_design_plan_impl_stack_orc_compiles_with_phase_family_contracts` already acts as the current family regression compile guard and should remain a guard, not become the place where this slice rewrites the migration family.

## Hard Scope Limits

Implement only this bounded slice:

- add one explicit authored Workflow Lisp expression form for constructing one declared union variant;
- elaborate that authored form directly to `UnionVariantExpr`;
- typecheck the form against ordinary declared union metadata and existing variant-field rules;
- prove ordinary wrapper workflows can return a wrapper union and feed `resume-or-start :valid-when (APPROVED)`;
- keep source maps and authored provenance on the new surface so the constructed union remains reviewable and debuggable;
- add focused tests and one focused reusable-wrapper fixture for the new surface.

Explicit non-goals:

- no entrypoint context bootstrap, runtime-owned `RunCtx` / `PhaseCtx` creation, or public-input hiding for promoted entry workflows;
- no generic parametric specialization, structural constraints, imported-procedure polymorphism, runtime type values, or new anonymous/inferred unions;
- no redesign of `resume-or-start`, reusable-state adapters, review-loop lowering, findings dataflow, command-result bundle ownership, or parity-report generation;
- no command adapters, inline Python/shell glue, report parsing, pointer-as-state compatibility, or family-specific compiler intrinsics;
- no rewrites of `workflows/examples/design_plan_impl_review_stack_v2_call.orc` or the tracked family library workflows as part of this prerequisite slice;
- no runtime executor, state manager, or shared workflow-engine changes unless a focused failing test proves the frontend assumption is false.

## File Ownership

Modify:

- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/functions.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_key_migrations.py`
- Create: `tests/fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start_reusable_wrapper.orc`

Inspect and modify only if a focused failing test proves the need:

- `orchestrator/workflow_lisp/lowering.py`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/lisp_workflow_drafting_guide.md`

Do not modify unless verification proves this plan is incomplete:

- `orchestrator/workflow_lisp/phase_stdlib.py`
- `orchestrator/workflow_lisp/adapters/validate_reusable_phase_state.py`
- `orchestrator/workflow_lisp/adapters/write_reusable_phase_state_v1.py`
- `orchestrator/workflow/executor.py`
- `orchestrator/workflow/loaded_bundle.py`
- `workflows/examples/design_plan_impl_review_stack_v2_call.orc`
- `specs/dsl.md`
- `specs/state.md`

## Required Surface Contract

These are fixed implementation decisions for this slice:

- The authored constructor surface is:

```lisp
(variant <UnionType> <VariantName> :field_a expr_a :field_b expr_b)
```

- `<UnionType>` must resolve to a declared union type.
- `<VariantName>` must name exactly one declared variant on that union.
- Fields use the same explicit keyword/value pair shape as `record`; no positional or inferred variant payloads are allowed.
- Elaboration must produce the existing `UnionVariantExpr` node rather than a new authored-only runtime node or a second lowering representation.
- The resulting expression type is the declared union type, not a synthetic per-variant type.
- Constructing a union value does not establish proof for later field access; variant-specific field reads still require `match`, `requires_variant`, or another already-accepted proof-bearing path.
- Diagnostics should reuse existing codes and taxonomy where possible:
  - unknown union type or non-union constructor target -> existing type mismatch path
  - unknown variant -> `union_variant_unknown`
  - missing required field -> existing missing-field diagnostic
  - duplicate field -> existing duplicate-field diagnostic
  - unknown or forbidden field -> existing unknown-field diagnostic
  - field type mismatch -> existing type mismatch path
- Thin macros, generated helpers, and future specialization outputs may target the new authored surface or directly emit the same `UnionVariantExpr`; they must not depend on a family-specific compiler branch.

## Implementation Units

### Unit 1: Authored Union Constructor Surface

Owns parsing/elaboration of the new authored form.

Files:

- `orchestrator/workflow_lisp/expressions.py`
- `tests/test_workflow_lisp_procedures.py`

Stable contract:

- ordinary expression elaboration recognizes `variant` alongside `record`;
- the elaborated node is `UnionVariantExpr` with authored span, form path, and expansion provenance;
- `UnionVariantExpr` docstrings/comments no longer claim compiler-generated-only ownership.

### Unit 2: Union Typecheck Reuse

Owns validation of the authored surface against declared union metadata.

Files:

- `orchestrator/workflow_lisp/typecheck.py`
- `tests/test_workflow_lisp_procedures.py`

Stable contract:

- authored `variant` construction reuses existing union-field validation rules;
- no new proof model or runtime value model is introduced;
- invalid authored wrappers fail in the frontend with stable diagnostics.

### Unit 3: Wrapper-Level Resume Proof

Owns the focused reusable-wrapper fixture and the proof that wrapper unions can drive approved-only reuse.

Files:

- `tests/fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start_reusable_wrapper.orc`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_key_migrations.py`

Stable contract:

- a wrapper workflow can `match` on an inner union and return a different authored wrapper union using the new surface;
- an outer workflow can use `resume-or-start :valid-when (APPROVED)` over that wrapper union;
- existing migration family compile coverage still passes unchanged.

### Unit 4: Lowering And Public-Contract Alignment

Owns any minimal follow-up changes required only if authored-node provenance or docs prove incomplete once tests are in place.

Files:

- `orchestrator/workflow_lisp/lowering.py` only if failing tests show authored-node source-map/lowering gaps
- `docs/design/workflow_lisp_frontend_specification.md` only if the new surface ships as current-checkout behavior
- `docs/lisp_workflow_drafting_guide.md` only if the new surface ships as current authoring guidance

Stable contract:

- lowering continues to flow through the existing `UnionVariantExpr` path;
- docs, if updated, describe the bounded authored `variant` surface without broadening scope into parametric specialization or runtime union inference.

## Task Checklist

### Task 1: Lock The Failing Surface With Frontend Tests First

**Files:**

- Modify: `tests/test_workflow_lisp_procedures.py`

- [ ] Add positive elaboration coverage proving ordinary `.orc` source can author `(variant ...)` and the compiled expression tree contains `UnionVariantExpr` rather than a new expression class.
- [ ] Add focused typecheck negatives for:
  - non-union constructor targets
  - unknown variants
  - missing required fields
  - unknown fields
  - duplicate fields
  - field type mismatch
- [ ] Add one positive test proving the authored constructor remains pure when its field expressions are pure, reusing the existing aggregate purity path.
- [ ] Prefer inline module snippets in `tests/test_workflow_lisp_procedures.py` unless an invalid fixture materially improves diagnostic clarity.

Suggested test additions:

- `test_compile_stage3_elaborates_authored_variant_constructor_to_union_variant_expr`
- `test_typecheck_authored_variant_constructor_rejects_non_union_target`
- `test_typecheck_authored_variant_constructor_rejects_unknown_variant`
- `test_typecheck_authored_variant_constructor_rejects_missing_required_field`
- `test_typecheck_authored_variant_constructor_rejects_unknown_field`
- `test_typecheck_authored_variant_constructor_rejects_duplicate_field`
- `test_typecheck_authored_variant_constructor_rejects_field_type_mismatch`

**Blocking verification after Task 1:**

- [ ] Run:
  - `python -m pytest --collect-only tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_key_migrations.py -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_procedures.py -k "union_variant or reusable_wrapper" -q`

Expected before implementation: the new positive authored-`variant` tests fail because ordinary expression elaboration still rejects the `variant` head or never produces an authored `UnionVariantExpr`.

### Task 2: Expose The Authored Constructor In Expression Elaboration

**Files:**

- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/functions.py`
- Modify: `tests/test_workflow_lisp_procedures.py`

- [ ] Add `variant` head handling in `_elaborate_list(...)` next to `record`.
- [ ] Implement one `_elaborate_variant(...)` helper that:
  - requires a union type symbol,
  - requires a variant-name symbol,
  - requires keyword/value field pairs,
  - elaborates field payloads through the existing recursive expression path, and
  - returns `UnionVariantExpr`.
- [ ] Update `UnionVariantExpr` documentation/comments so the node is no longer described as compiler-generated-only.
- [ ] Keep authored provenance intact by preserving the authored form span, form path, and expansion stack on the emitted `UnionVariantExpr`.
- [ ] Confirm helper/classification utilities continue to treat the node as a pure aggregate expression when its children are pure.

Implementation guardrails:

- Do not add a new `AuthoredUnionVariantExpr` or a second runtime representation.
- Do not infer the union type or variant name from context in this first slice.
- Do not accept record-like shorthand such as `(VariantName ...)` or positional payloads.

**Blocking verification after Task 2:**

- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_procedures.py -k "union_variant or reusable_wrapper" -q`

Expected after Task 2: authored `variant` source elaborates to `UnionVariantExpr`, but some negative diagnostics or wrapper-level reuse tests may still fail until the typecheck/fixture work lands.

### Task 3: Reuse Existing Union Typecheck And Lowering Semantics

**Files:**

- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Inspect and modify only if needed: `orchestrator/workflow_lisp/lowering.py`
- Modify: `tests/test_workflow_lisp_procedures.py`

- [ ] Make the authored surface typecheck through the existing `UnionVariantExpr` path without adding a second validation branch keyed to workflow family names.
- [ ] Reuse the current union metadata lookup so the returned expression type is the declared union type.
- [ ] Reuse existing field validation rules and diagnostic codes instead of inventing wrapper-specific diagnostics.
- [ ] Add one assertion path in tests proving lowering/source-map behavior still flows through the existing `UnionVariantExpr` machinery. Prefer inspecting typed nodes and existing lowered union outputs over inventing new debug-only plumbing.
- [ ] Touch `orchestrator/workflow_lisp/lowering.py` only if a focused failing test proves authored-node provenance is missing after elaboration/typecheck changes.

Implementation guardrails:

- Do not weaken variant-proof rules for later field access.
- Do not special-case `resume-or-start`, wrapper workflows, or review-loop-generated helpers here.
- Do not make lowering depend on whether the node came from authored code or compiler synthesis.

**Blocking verification after Task 3:**

- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_procedures.py -k "union_variant or reusable_wrapper" -q`

Expected after Task 3: positive and negative authored union-construction tests pass, and no new lowering-only representation has been introduced.

### Task 4: Prove Wrapper-Level Approved-Only Reuse With A Focused Fixture

**Files:**

- Create: `tests/fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start_reusable_wrapper.orc`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_key_migrations.py`

- [ ] Add a new focused valid fixture instead of widening `phase_stdlib_resume_or_start.orc`.
- [ ] In that fixture, define:
  - an inner union-returning workflow such as `plan-run`,
  - a wrapper union type distinct from the inner return union,
  - a wrapper workflow that `match`es the inner result and returns authored `(variant ...)` values for each branch, and
  - an outer workflow that uses `resume-or-start :valid-when (APPROVED)` over the wrapper union.
- [ ] Keep explicit `phase_ctx` and explicit resume inputs in the fixture; do not mix in the separate entrypoint-context-bootstrap gap.
- [ ] Add focused phase-stdlib tests proving the wrapper result compiles, lowers, and remains legal input to `resume-or-start`.
- [ ] Keep `tests/test_workflow_lisp_key_migrations.py::test_design_plan_impl_stack_orc_compiles_with_phase_family_contracts` as a compile-only regression guard so this slice proves it did not break the current migration family.
- [ ] If useful, extend `test_resume_or_start_plan_gate_reusable_state_parity_path` or add a similarly narrow assertion name that covers wrapper-level approved-only union reuse without editing the real family workflow.

Suggested test additions:

- `test_resume_or_start_supports_authored_reusable_wrapper_union`
- `test_resume_or_start_wrapper_union_reuses_existing_union_lowering_contract`

**Blocking verification after Task 4:**

- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "resume_plan_gate or reusable_wrapper or resume_or_start" -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "design_plan_impl_stack_orc_compiles_with_phase_family_contracts or resume_or_start_plan_gate_reusable_state_parity_path" -q`

Expected after Task 4: a focused wrapper workflow can return an authored wrapper union and drive approved-only `resume-or-start`, while the current migration family still compiles unchanged.

### Task 5: Align Current-Checkout Docs Only If The Surface Ships

**Files:**

- Inspect and modify only if needed: `docs/design/workflow_lisp_frontend_specification.md`
- Inspect and modify only if needed: `docs/lisp_workflow_drafting_guide.md`

- [ ] Update the baseline frontend specification if the authored `variant` surface becomes accepted current-checkout behavior.
- [ ] Update the drafting guide to show when authors should use `variant` instead of record-only wrapper normalization.
- [ ] Keep both doc updates narrow: describe the explicit authored constructor form and its proof limits, but do not broaden into parametric specialization, runtime type values, or new union inference claims.

Docs guardrails:

- Do not claim the slice solves entrypoint context bootstrap.
- Do not claim generic specialization or review-loop parity is complete because this authored constructor exists.
- Do not add prompt-text or prose-only tests.

### Task 6: Run The Recorded Narrow Verification Set

**Files:**

- No new maintained source files; this task proves the bounded slice with the recorded commands.

- [ ] Run the exact collect-only command from `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/0/design-gap-architect/check_commands.json`:
  - `python -m pytest --collect-only tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_key_migrations.py -q`
- [ ] Run the exact authored-union focused command:
  - `python -m pytest tests/test_workflow_lisp_procedures.py -k "union_variant or reusable_wrapper" -q`
- [ ] Run the exact resume/reusable-wrapper focused command:
  - `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "resume_plan_gate or reusable_wrapper or resume_or_start" -q`
- [ ] Run the exact migration regression command:
  - `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "design_plan_impl_stack_orc_compiles_with_phase_family_contracts or resume_or_start_plan_gate_reusable_state_parity_path" -q`
- [ ] Run the exact compile regression command:
  - `python -m orchestrator compile workflows/examples/design_plan_impl_review_stack_v2_call.orc --entry-workflow design-plan-impl-review-stack --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.commands.json`

Completion evidence required before closing the task:

- [ ] The new authored `variant` surface is implemented through `UnionVariantExpr`, not a parallel runtime form.
- [ ] Invalid authored union construction fails with stable frontend diagnostics.
- [ ] The focused wrapper fixture proves approved-only wrapper reuse through an authored union result.
- [ ] The current `design_plan_impl_stack` compile guard still passes without family-specific workflow edits.
- [ ] Any doc updates remain bounded to the new authored constructor surface.
