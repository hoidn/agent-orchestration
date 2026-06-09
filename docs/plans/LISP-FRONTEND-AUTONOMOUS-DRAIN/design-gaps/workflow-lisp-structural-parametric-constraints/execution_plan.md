# Workflow Lisp Structural Parametric Constraints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement first-tranche `defproc :where` structural constraints so generic procedures can validate caller shapes before specialization, support branch-free `has-shared-union-field` access, preserve visible effect boundaries for constrained ProcRef-selected generic behavior, and keep the current review-loop bridge unchanged.

**Architecture:** The current checkout already has the needed preconditions: `:forall` parsing, `TypeParamRef`, specialization plumbing, `procedure_typecheck.py`, `procedure_specialization.py`, and the split typecheck owners (`typecheck_context.py`, `typecheck_dispatch.py`, `typecheck_proofs.py`). Build the missing slice by keeping `procedures.py` as the parser owner, adding `parametric_constraints.py` as the constraint-semantics owner, integrating concrete checks in `procedure_typecheck.py` before specialization acceptance, and threading only a compile-time shared-field capability into specialized-helper typechecking. Prove the slice with both pure and effectful generic fixtures so constrained ProcRef-selected helpers still lower through ordinary visible `provider-result`, `command-result`, or certified-adapter boundaries. Do not widen into stdlib review-loop migration, bridge removal, runtime redesign, or new generic surfaces.

**Tech Stack:** Python 3, pytest, Workflow Lisp frontend modules under `orchestrator/workflow_lisp/`, repo docs under `docs/`, and repo-root verification commands.

---

## Fixed Inputs

Read these before implementing and treat the design docs as authority:

- `docs/index.md`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
- `docs/design/workflow_lisp_structural_parametric_constraints.md`
- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/design/workflow_lisp_refactor_architecture.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-structural-parametric-constraints/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/4/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

## Scope Guard

In scope:

- `is-record`
- `is-union`
- `has-field`
- `has-union-variant`
- `has-shared-union-field`
- richer stored `:where` metadata that can represent variant field requirements
- concrete-type checking before specialization acceptance
- narrow branch-free shared-union-field access only

Out of scope:

- new `:forall` syntax or generic inference work
- generic `defworkflow`
- ordinary stdlib `review-revise-loop` authoring in `std/phase.orc`
- removal of `__stdlib-specialization__ phase-review-loop`
- loop exhaustion projection
- caller-owned terminal construction
- runtime/shared-validation redesign

## File Map

- Create: `orchestrator/workflow_lisp/parametric_constraints.py`
  Constraint normalization, concrete checking, capability derivation, and focused helper rendering for diagnostics.
- Modify: `orchestrator/workflow_lisp/procedures.py`
  Keep `defproc` header parsing ownership, but replace flat `ProcedureConstraintSyntax.args` with structured metadata that can encode `has-union-variant` field requirements.
- Modify: `orchestrator/workflow_lisp/procedure_typecheck.py`
  Replace `unsupported_parametric_constraint_surface` with real constraint checking after type binding inference and before specialization requests are accepted.
- Modify: `orchestrator/workflow_lisp/procedure_specialization.py`
  Carry successful compile-time structural capabilities into specialized helpers without leaking them into runtime-visible surfaces.
- Modify: `orchestrator/workflow_lisp/typecheck_context.py`
  Add a compile-time-only slot for shared-union-field capabilities on the active typecheck context.
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py`
  Thread the new capability set through recursive typechecking context creation.
- Modify: `orchestrator/workflow_lisp/typecheck_proofs.py`
  Allow exact branch-free access only for validated shared union fields while keeping ordinary variant proof unchanged.
- Modify: `orchestrator/workflow_lisp/diagnostics.py`
  Register any new structural-constraint diagnostics with the correct validation phase.
- Modify: `tests/test_workflow_lisp_procedures.py`
  Parser, compile-time constraint, specialization, validated-bundle, and effect-visibility coverage.
- Modify: `tests/test_workflow_lisp_expressions.py`
  Narrow shared-field access hook coverage and proof-regression checks.
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
  Regression proof that the existing review-loop bridge still compiles unchanged after the new generic mechanism lands.
- Modify: `docs/lisp_workflow_drafting_guide.md`
  Author-facing documentation for the first-tranche `:where` surface and the exact `has-shared-union-field` limitation.

### Task 1: Reshape Stored `:where` Metadata

**Files:**

- Modify: `orchestrator/workflow_lisp/procedures.py`
- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Test: `tests/test_workflow_lisp_procedures.py`

- [ ] **Step 1: Replace the flat-metadata tests with structured-clause tests**

Add or rewrite focused tests in `tests/test_workflow_lisp_procedures.py` for:

- `test_elaborate_defproc_parses_structured_where_metadata`
- `test_elaborate_defproc_parses_has_union_variant_field_requirements`
- `test_elaborate_defproc_rejects_malformed_where_variant_field_requirements`
- `test_elaborate_defproc_rejects_unknown_where_subject_type_param`

Use inline `_write_module(...)` fixtures, not new on-disk `.orc` fixtures.

- [ ] **Step 2: Run the parser-only selectors first**

Run:

```bash
pytest \
  tests/test_workflow_lisp_procedures.py::test_elaborate_defproc_parses_structured_where_metadata \
  tests/test_workflow_lisp_procedures.py::test_elaborate_defproc_parses_has_union_variant_field_requirements \
  tests/test_workflow_lisp_procedures.py::test_elaborate_defproc_rejects_malformed_where_variant_field_requirements \
  tests/test_workflow_lisp_procedures.py::test_elaborate_defproc_rejects_unknown_where_subject_type_param \
  -q
```

Expected: FAIL because `ProcedureConstraintSyntax` still stores only flat string args.

- [ ] **Step 3: Replace flat clause payloads with structured metadata**

In `orchestrator/workflow_lisp/procedures.py`:

- keep clause-order validation exactly as-is
- keep undeclared-type-param validation exactly as-is
- replace flat `args: tuple[str, ...]` with structured operands that can represent:
  - zero-operand kind constraints
  - `has-field` name/type pairs
  - `has-shared-union-field` name/type pairs
  - `has-union-variant VARIANT`
  - `has-union-variant VARIANT (field Type ...)`
- keep the stored representation syntax-preserving enough that later normalization can report authored spans against the original clause

In `orchestrator/workflow_lisp/diagnostics.py`, register any new clause-shape diagnostic codes needed for malformed structured operands.

- [ ] **Step 4: Re-run the parser selectors**

Run the same `pytest` command from Step 2.

Expected: PASS.

- [ ] **Step 5: Confirm no flat `.args` callers are left behind accidentally**

Run:

```bash
rg -n "\.args\b|constraint_name" orchestrator/workflow_lisp tests/test_workflow_lisp_procedures.py
```

Expected: any remaining callers are intentional compatibility accesses you still plan to remove in later tasks, not stale flat-string assumptions.

### Task 2: Add Concrete Structural Constraint Checking

**Files:**

- Create: `orchestrator/workflow_lisp/parametric_constraints.py`
- Modify: `orchestrator/workflow_lisp/procedure_typecheck.py`
- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Test: `tests/test_workflow_lisp_procedures.py`

- [ ] **Step 1: Add failing compile-time tests for the supported first-tranche vocabulary**

In `tests/test_workflow_lisp_procedures.py`, add or rewrite focused compile tests for:

- `test_compile_stage3_accepts_is_record_and_has_field_constraints`
- `test_compile_stage3_accepts_has_union_variant_with_field_requirements`
- `test_compile_stage3_rejects_unknown_structural_constraint`
- `test_compile_stage3_rejects_unsatisfied_has_field_constraint`
- `test_compile_stage3_rejects_unsatisfied_has_union_variant_constraint`
- `test_compile_stage3_rejects_unsatisfied_shared_union_field_constraint`

Replace the old rejection-only test `test_compile_stage3_rejects_nonempty_where_before_structural_constraints_land` with positive and negative constraint coverage.

- [ ] **Step 2: Run the focused compile selectors**

Run:

```bash
pytest \
  tests/test_workflow_lisp_procedures.py::test_compile_stage3_accepts_is_record_and_has_field_constraints \
  tests/test_workflow_lisp_procedures.py::test_compile_stage3_accepts_has_union_variant_with_field_requirements \
  tests/test_workflow_lisp_procedures.py::test_compile_stage3_rejects_unknown_structural_constraint \
  tests/test_workflow_lisp_procedures.py::test_compile_stage3_rejects_unsatisfied_has_field_constraint \
  tests/test_workflow_lisp_procedures.py::test_compile_stage3_rejects_unsatisfied_has_union_variant_constraint \
  tests/test_workflow_lisp_procedures.py::test_compile_stage3_rejects_unsatisfied_shared_union_field_constraint \
  -q
```

Expected: FAIL because `procedure_typecheck.py` still raises `unsupported_parametric_constraint_surface`.

- [ ] **Step 3: Implement the dedicated constraint owner module**

Create `orchestrator/workflow_lisp/parametric_constraints.py` with:

- normalized dataclasses for first-tranche constraints
- normalization from the parsed `procedures.py` metadata
- concrete checking helpers that consume resolved `TypeRef` bindings only
- exact resolved-`TypeRef` compatibility checks for field types
- compile-time capability output for successful `has-shared-union-field`
- fail-closed diagnostics for malformed, unknown, and unsatisfied constraints

Do not add runtime state, runtime type values, or review-loop-specific logic.

- [ ] **Step 4: Integrate the checker into generic call acceptance**

In `orchestrator/workflow_lisp/procedure_typecheck.py`:

- after `_infer_parametric_type_bindings(...)` and unresolved-binding checks, normalize and evaluate `signature.where_clauses`
- remove the blanket `unsupported_parametric_constraint_surface` path
- keep the existing pipeline order:
  constraint check -> request specialization -> typecheck instantiated helper -> lower
- store the returned shared-field capability set on the pending specialization request as compile-time-only metadata

- [ ] **Step 5: Re-run the focused compile selectors**

Run the same `pytest` command from Step 2.

Expected: PASS.

### Task 3: Thread Shared-Union-Field Capability Into Specialized Helper Typing

**Files:**

- Modify: `orchestrator/workflow_lisp/procedure_typecheck.py`
- Modify: `orchestrator/workflow_lisp/procedure_specialization.py`
- Modify: `orchestrator/workflow_lisp/typecheck_context.py`
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Modify: `orchestrator/workflow_lisp/typecheck_proofs.py`
- Test: `tests/test_workflow_lisp_expressions.py`
- Test: `tests/test_workflow_lisp_procedures.py`

- [ ] **Step 1: Add failing tests for the narrow branch-free access hook**

Add tests for:

- `test_shared_union_field_capability_allows_branch_free_projection_only_for_validated_field`
- `test_shared_union_field_capability_does_not_allow_variant_specific_field_without_match`
- `test_compile_stage3_accepts_generic_shared_union_field_projection`

Keep these tests narrow: the new capability should authorize only the named shared field and should not act as a second general proof system.

- [ ] **Step 2: Run the new selectors**

Run:

```bash
pytest \
  tests/test_workflow_lisp_expressions.py::test_shared_union_field_capability_allows_branch_free_projection_only_for_validated_field \
  tests/test_workflow_lisp_expressions.py::test_shared_union_field_capability_does_not_allow_variant_specific_field_without_match \
  tests/test_workflow_lisp_procedures.py::test_compile_stage3_accepts_generic_shared_union_field_projection \
  -q
```

Expected: FAIL because the typecheck context has no structural capability channel and `resolve_field_access(...)` still rejects all union field access without proof.

- [ ] **Step 3: Carry compile-time capability metadata through specialization**

In `procedure_typecheck.py` and `procedure_specialization.py`:

- extend the pending specialization request and specialized procedure metadata with the validated shared-field capability set
- keep the metadata compile-time-only
- ensure monomorphic signatures and generated helper names remain unchanged except for carrying the new capability metadata internally

- [ ] **Step 4: Teach the proof owner about the validated shared field**

In `typecheck_context.py`, `typecheck_dispatch.py`, and `typecheck_proofs.py`:

- add a context slot for shared-union-field capabilities
- thread it through recursive typechecking calls
- in `resolve_field_access(...)`, allow branch-free access only when:
  - the base type is the exact concrete union validated by the constraint
  - the accessed field is the exact validated shared field
  - the returned field type is the validated common field type
- preserve existing `variant_ref_unproved` and `variant_ref_wrong_variant` behavior for all other union fields

- [ ] **Step 5: Re-run the new selectors**

Run the same `pytest` command from Step 2.

Expected: PASS.

### Task 4: Prove End-To-End Generic Use, Effect Boundaries, And Protect Existing Review-Loop Behavior

**Files:**

- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] **Step 1: Add a validated-bundle integration test for a real generic workflow body**

In `tests/test_workflow_lisp_procedures.py`, add one `compile_stage3_module(..., validate_shared=True, ...)` test that:

- uses a non-review generic `defproc` with supported `:where` constraints
- produces a validated bundle
- proves specialization remains monomorphic
- proves no runtime-visible type parameters leak

Prefer inline module text via `_write_module(...)`.

- [ ] **Step 2: Add an effectful generic ProcRef integration test with visible effect boundaries**

In `tests/test_workflow_lisp_procedures.py`, add one constrained generic integration test that:

- uses ProcRef-selected behavior with supported `:where` constraints
- lowers through existing `provider-result`, `command-result`, or certified-adapter surfaces already supported by the checkout
- proves structural-constraint checking does not hide or rewrite those effect boundaries
- proves provider/command/adaptor visibility remains the same after specialization
- avoids inventing new adapters, runtime effects, or review-loop-specific paths

Prefer inline module text via `_write_module(...)` and assert against existing validated compile/lowering surfaces rather than report parsing or debug-only views.

- [ ] **Step 3: Add a bridge-regression test in the phase stdlib suite**

In `tests/test_workflow_lisp_phase_stdlib.py`, add or extend a test around `VALID_REVIEW_LOOP_FIXTURE` proving:

- the existing `__stdlib-specialization__ phase-review-loop` bridge still compiles unchanged
- structural-constraint support does not silently route `review-revise-loop` through a new path

- [ ] **Step 4: Run the targeted integration selectors**

Run:

```bash
pytest \
  tests/test_workflow_lisp_procedures.py::test_compile_stage3_validates_generic_where_workflow_bundle \
  tests/test_workflow_lisp_procedures.py::test_compile_stage3_preserves_effect_visibility_for_constrained_generic_procref_fixture \
  tests/test_workflow_lisp_phase_stdlib.py::test_phase_stdlib_review_loop_bridge_still_compiles_after_structural_constraints \
  -q
```

Expected: PASS.

- [ ] **Step 5: Run a focused regression band across the touched suites**

Run:

```bash
pytest \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  -q
```

Expected: PASS.

- [ ] **Step 6: If a failure appears, classify it before widening scope**

Use the repo rule from `AGENTS.md`:

- selected-slice regression: fix now
- unrelated touched-surface failure: record and fix only if required to restore this slice
- pre-existing unrelated failure: record exact selector and do not widen the slice

### Task 5: Update Authoring Docs And Finish Verification

**Files:**

- Modify: `docs/lisp_workflow_drafting_guide.md`
- Verify: `tests/test_workflow_lisp_procedures.py`
- Verify: `tests/test_workflow_lisp_expressions.py`
- Verify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] **Step 1: Document the first-tranche `:where` contract**

Update `docs/lisp_workflow_drafting_guide.md` with:

- the supported first-tranche constraint spellings only
- the clause order `:forall`, params, `:where`, `->`
- the exact limitation of `has-shared-union-field`
- a reminder that variant-specific fields still require `match`

- [ ] **Step 2: Run collect-only on every touched test module**

Run:

```bash
pytest --collect-only \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  -q
```

Expected: PASS.

- [ ] **Step 3: Run frontend compile sanity**

Run:

```bash
python -m compileall orchestrator/workflow_lisp
```

Expected: PASS.

- [ ] **Step 4: Run whitespace and patch hygiene checks**

Run:

```bash
git diff --check
```

Expected: PASS.

- [ ] **Step 5: Record the verification summary in the implementation notes**

Capture:

- exact pytest selectors run
- whether the validated-bundle integration test passed
- whether the effectful generic ProcRef visibility test passed
- that the legacy review-loop bridge remained unchanged
- any explicitly classified residual failures, if they exist

## Completion Criteria

Do not call this slice complete until all of the following are true:

- non-empty `:where` clauses no longer fail by default
- only the owner-doc vocabulary is accepted
- malformed, unknown, and unsatisfied constraints fail before specialization acceptance
- specialization still produces monomorphic helpers with no runtime type-parameter leaks
- `has-shared-union-field` enables only the validated branch-free field projection
- variant-specific fields still require ordinary proof-bearing `match`
- at least one non-review generic workflow compiles through shared validation
- at least one non-review effectful generic ProcRef fixture preserves visible `provider-result`, `command-result`, or certified-adapter boundaries after specialization
- the current review-loop bridge still compiles unchanged
- authoring docs reflect the new first-tranche surface
