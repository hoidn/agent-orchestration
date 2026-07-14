# Procedure-First Effect Substrate Implementation Plan

Status: complete and gated 2026-07-13

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Completion note (2026-07-13):** Tasks 1–5 are implemented. Fresh focused,
> route/composition, and broad verification preserved every caller-visible
> effect and the no-family-change boundary. Independent whole-plan review
> returned **SPEC PASS** and **QUALITY PASS** with no open findings. This plan
> is historical execution evidence and must not be replayed; the current
> selector is `2026-07-13-procedure-first-pilot-plan.md`.

**Goal:** Represent a procedure's body-local direct effects separately from its caller-visible transitive effects, recompute the latter after generic and `ProcRef` resolution, and make lowering and Semantic IR consume the resolved view without changing any currently visible effect.

**Architecture:** Keep `EffectSummary` as the shared effect algebra and make a procedure-call expression contribute a call edge plus callee effects only to the transitive view. Authoritative post-specialization typechecking and the existing call-graph closure then rebuild each monomorphic procedure's caller-visible summary before lowering; inline and private-workflow lowering receive that resolved summary, while lexical direct effects remain available for diagnostics and declaration checks. This plan changes compiler substrate only—no workflow family, provider, command, artifact, checkpoint, or public contract is migrated here.

**Tech Stack:** Python 3 dataclasses, Workflow Lisp typechecking/specialization/lowering, Semantic IR, pytest.

---

## Authority, prerequisites, and boundaries

- Accepted contract: `docs/design/workflow_lisp_procedure_first_reuse_contract.md`
- Parent frontend specification: `docs/design/workflow_lisp_frontend_specification.md`
- Effect component contract: `docs/design/workflow_lisp_effect_graph.md`
- Required order: execute after `docs/plans/2026-07-10-workflow-lisp-typed-result-guidance-plan.md` and before `docs/plans/2026-07-13-procedure-first-pilot-plan.md`.
- Preserve the public meaning of `TypedProcedureDef.direct_effect_summary` and `TypedProcedureDef.transitive_effect_summary`; do not create a second effect atom hierarchy.
- Preserve every effect currently visible at a caller. A missing effect is a release blocker even when lowered steps happen to expose the operation structurally.
- Do not modify `workflows/**`, family parity manifests, route-readiness registries, YAML retirement state, or public DSL versions in this plan.
- Run from the repository root. Do not create a worktree. Stage only files named by the active task.

## Protected working-tree guard

The following user-owned dirty paths are outside every task in this plan:

- `docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md`
- `docs/plans/2026-07-01-workflow-audit-tier-fixes.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md`
- `state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt`
- `tests/test_workflow_non_progress_step_back_demo.py`
- `workflows/examples/non_progress_step_back_demo.yaml`
- `workflows/library/prompts/workflow_step_back/diagnose_non_progress.md`

Before every commit, run `git diff --cached --name-only`, then run:

```bash
git diff --cached --name-only -- \
  'docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md' \
  'docs/plans/2026-07-01-workflow-audit-tier-fixes.md' \
  'docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md' \
  'state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt' \
  'tests/test_workflow_non_progress_step_back_demo.py' \
  'workflows/examples/non_progress_step_back_demo.yaml' \
  'workflows/library/prompts/workflow_step_back/diagnose_non_progress.md'
```

The literal protected-path command must print nothing; the full staged list
must be a subset of the active task's `Files` list. Never stage, restore, or
rewrite a protected path. Record its initial `git status --short` output only
as a guard baseline; user changes to those paths are not plan failures.

## File responsibility map

- `orchestrator/workflow_lisp/effects.py`: one canonical constructor for a procedure-call edge whose callee effects are transitive, not body-local.
- `orchestrator/workflow_lisp/procedure_typecheck.py`: apply that constructor to direct, bound-`ProcRef`, and parametric/specialized calls.
- `orchestrator/workflow_lisp/procedure_specialization.py`: ensure specialized monomorphic procedures do not retain a stale pre-resolution effect summary.
- `orchestrator/workflow_lisp/compiler.py`: recompute call-graph closure after specialization and hand the resolved procedures to lowering.
- `orchestrator/workflow_lisp/lowering/procedures.py`: consume the caller-visible transitive summary for inline/private-workflow fragments.
- `tests/test_workflow_lisp_procedures.py`: direct/transitive algebra, generic, `ProcRef`, declaration, and lowering regression coverage.
- `tests/test_workflow_lisp_build_artifacts.py`: serialized Semantic IR proof that resolved effects remain visible.

### Task 1: Characterize The Direct/Transitive Split

**Files:**
- Modify: `tests/test_workflow_lisp_procedures.py`

- [ ] **Step 1: Add a RED ordinary-call test**

Add a minimal module with an effectful `run-checks` procedure and an otherwise effect-free `invoke-checks` procedure that calls it. Assert all three facts:

```python
assert invoke.direct_effect_summary.direct_effects == frozenset()
assert invoke.direct_effect_summary.procedure_edges
assert UsesCommandEffect(subject=("run_checks",)) in invoke.transitive_effect_summary.transitive_effects
```

Also assert the public entry workflow still exposes `UsesCommandEffect("run_checks")`.

- [ ] **Step 2: Run the RED test**

```bash
pytest -q tests/test_workflow_lisp_procedures.py -k 'body_local_direct_effects'
```

Expected: FAIL because a procedure call currently copies the callee's transitive effects into `direct_effects`.

- [ ] **Step 3: Add RED generic and `ProcRef` specialization assertions**

Extend `test_compile_stage3_preserves_effect_visibility_for_constrained_generic_procref_fixture` and `test_stage3_materializes_proc_ref_specializations_before_lowering_and_preserves_effects` so the specialized wrapper has no body-local provider/command atom, retains its resolved procedure edge, and exposes the selected hook effect transitively.

- [ ] **Step 4: Run the complete RED selector**

```bash
pytest -q tests/test_workflow_lisp_procedures.py -k 'body_local_direct_effects or preserves_effect_visibility_for_constrained_generic_procref_fixture or materializes_proc_ref_specializations_before_lowering_and_preserves_effects'
```

Expected: at least the new direct-view assertions FAIL while existing transitive-view assertions remain green.

- [ ] **Step 5: Commit tests only**

```bash
git add tests/test_workflow_lisp_procedures.py
git commit -m "test: specify procedure direct and transitive effects"
```

### Task 2: Make Procedure Calls Transitive-Only At The Call Site

**Files:**
- Modify: `orchestrator/workflow_lisp/effects.py`
- Modify: `orchestrator/workflow_lisp/procedure_typecheck.py`
- Test: `tests/test_workflow_lisp_procedures.py`

- [ ] **Step 1: Add one canonical call-summary constructor**

Add a focused helper in `effects.py`:

```python
def effect_summary_from_procedure_call(
    *,
    callee_effects: Iterable[EffectAtom],
    edge: ProcedureCallEdge,
) -> EffectSummary:
    return effect_summary(
        direct_effects=(),
        transitive_effects=callee_effects,
        procedure_edges=(edge,),
    )
```

Do not change `merge_effect_summaries`; lexical child expressions must continue to union both views independently.

- [ ] **Step 2: Replace every callee-copy call path**

In `procedure_typecheck.py`, use the helper for:

- a bound `ProcRef` call;
- a non-generic named procedure call, including its resolved `ProcRef` specialization name; and
- a concrete parametric specialization call.

An unresolved compile-time `ProcRef` contributes no effect atom until specialization, as today; its authoritative specialized body must be handled in Task 3.

- [ ] **Step 3: Run the focused tests**

```bash
pytest -q tests/test_workflow_lisp_procedures.py -k 'body_local_direct_effects or effect_visibility or proc_ref_specializations or nested_proc_ref_effects'
```

Expected: PASS; no previously visible caller effect disappears.

- [ ] **Step 4: Run effect declaration diagnostics**

```bash
pytest -q tests/test_workflow_lisp_procedures.py -k 'declared_effect or inferred_effect or undeclared_effect or effects_clause'
```

Expected: PASS. Declaration validation remains based on the resolved transitive view.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/workflow_lisp/effects.py orchestrator/workflow_lisp/procedure_typecheck.py tests/test_workflow_lisp_procedures.py
git commit -m "Separate procedure call effects from lexical effects"
```

### Task 3: Recompute Effects After Generic And `ProcRef` Resolution

**Files:**
- Modify: `orchestrator/workflow_lisp/procedure_specialization.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify only if the re-typecheck carrier needs a focused seam: `orchestrator/workflow_lisp/procedure_typecheck.py`
- Test: `tests/test_workflow_lisp_procedures.py`

- [ ] **Step 1: Add a RED selected-hook differentiation test**

Compile the same generic procedure twice with two concrete hooks: one command-effect hook and one provider-effect hook. Assert each monomorphic specialization has the same body-local direct view but a different caller-visible transitive summary containing only its selected hook's effect. Also assert the generic declaration's body-local direct view is unchanged after both specializations.

- [ ] **Step 2: Run it RED**

```bash
pytest -q tests/test_workflow_lisp_procedures.py -k 'selected_hook_recomputes_transitive_effects'
```

Expected: FAIL if specialization copies the generic declaration's stale summaries.

- [ ] **Step 3: Make the specialized body authoritative**

After type, value, workflow-ref, and `ProcRef` bindings are resolved, authoritatively typecheck the monomorphic body with the resolved environments. Set its `direct_effect_summary` from that typed body, then run `_validate_procedure_effects_and_cycles` over the complete materialized procedure set. Do not copy `request.procedure.transitive_effect_summary` into a specialization as final truth.

The fixed point in `compiler.py` must finish specialization discovery and effect recomputation before `lower_typed_workflows` observes `typed_procedures`. Keep cycle diagnostics and declared-effect validation behavior unchanged.

- [ ] **Step 4: Prove call-graph closure and cycle diagnostics**

```bash
pytest -q tests/test_workflow_lisp_procedures.py -k 'selected_hook_recomputes_transitive_effects or specialization_cycle or proc_lowering_cycle or nested_proc_ref_effects or constrained_generic_procref'
```

Expected: PASS.

- [ ] **Step 5: Prove all currently supported effect families remain visible**

```bash
pytest -q tests/test_workflow_lisp_procedures.py -k 'provider or command or resource_transition or resume_or_start or finalize_selected_item or workflow_ref'
```

Expected: PASS. This is preservation evidence, not authorization to change a workflow family.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/workflow_lisp/procedure_specialization.py orchestrator/workflow_lisp/compiler.py orchestrator/workflow_lisp/procedure_typecheck.py tests/test_workflow_lisp_procedures.py
git commit -m "Recompute specialized procedure effects"
```

### Task 4: Feed Resolved Effects Into Lowering And Semantic IR

**Files:**
- Modify: `orchestrator/workflow_lisp/lowering/procedures.py`
- Modify only if serialization lacks the existing carrier: `orchestrator/workflow/semantic_ir.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] **Step 1: Add RED lowering assertions**

For both `:lowering inline` and `:lowering private-workflow`, assert the composition/private workflow effect carrier is the procedure's resolved `transitive_effect_summary`, not its body-local direct view. Use a wrapper procedure whose only effect comes from a selected effectful hook.

- [ ] **Step 2: Add RED Semantic IR assertions**

Build the frontend bundle for the same inline wrapper and assert the selected command/provider effect appears in `semantic_ir.effects` with procedure/call-site provenance, while an unselected hook effect does not. Also assert the serialized source map covers the generated effect node.

- [ ] **Step 3: Run RED tests**

```bash
pytest -q tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_build_artifacts.py -k 'resolved_transitive_effects or selected_hook_semantic_ir'
```

Expected: FAIL only where a lowering or Semantic IR carrier still reads the stale/direct view.

- [ ] **Step 4: Thread the resolved view minimally**

Keep `_private_workflow_from_procedure(...).effect_summary` and inline `CompositionFragment.effect_summary` on `procedure.transitive_effect_summary`. Change `semantic_ir.py` only if the existing lowered provenance cannot carry the effect; do not add procedure-specific Semantic IR entities when the existing effect/provenance entities suffice.

- [ ] **Step 5: Run focused source-map and Semantic IR suites**

```bash
pytest -q tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_source_map.py -k 'effect or proc_ref or procedure or generated_semantic'
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/workflow_lisp/lowering/procedures.py orchestrator/workflow/semantic_ir.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_build_artifacts.py
git commit -m "Expose resolved procedure effects to Semantic IR"
```

### Task 5: Verify The Substrate Gate

**Files:**
- Modify only for accurate current behavior: `docs/design/workflow_lisp_effect_graph.md`
- Modify only for accurate capability status: `docs/capability_status_matrix.md`

- [ ] **Step 1: Run focused collection and tests**

```bash
pytest --collect-only -q tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_build_artifacts.py
pytest -q tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_lowering.py
```

Expected: collection succeeds and focused suites PASS.

- [ ] **Step 2: Run route and composition regressions**

```bash
pytest -q tests/test_workflow_lisp_route_readiness.py tests/test_workflow_lisp_generic_stdlib_composition.py tests/test_workflow_lisp_imported_stdlib_macro_payload_helper_composition.py tests/test_workflow_lisp_key_migrations.py
```

Expected: PASS with no route or effect loss.

- [ ] **Step 3: Run the broad suite in tmux**

Use the `tmux` skill, then run:

```bash
pytest -q -n 16 --dist=worksteal
```

Expected: PASS except only already-established unrelated failures, which must be listed verbatim with fresh isolated reruns. Do not weaken or skip failing effect tests.

- [ ] **Step 4: Review the no-family-change boundary**

```bash
git diff --name-only HEAD~4..HEAD -- workflows
git diff --check HEAD~4..HEAD
```

Expected: the first command prints nothing; the committed-range whitespace
check exits 0 without inspecting protected working-tree changes.

- [ ] **Step 5: Commit documentation only if needed**

```bash
git add docs/design/workflow_lisp_effect_graph.md docs/capability_status_matrix.md
git commit -m "Document resolved procedure effect views"
```

Skip this commit when the existing docs are already exact.

- [ ] **Step 6: Obtain independent specification and quality reviews**

The specification reviewer checks the accepted direct/transitive semantics,
specialization timing, lowering/Semantic IR consumption, and absence of family
or return-contract changes. The quality reviewer checks test
non-tautology, owner boundaries, diagnostics/source-map preservation, commit
scope, and the protected working-tree guard. If either review fails, the
implementing agent fixes the cited task, reruns its focused and broad checks,
and both reviewers rerun the whole plan. Do not release the pilot until both
return PASS.

## Completion gate and stop conditions

The pilot may start only when direct-view RED tests, selected-hook specialization tests, lowering/Semantic IR tests, focused suites, and the broad suite have fresh evidence and independent specification plus quality reviews pass.

Stop and return to design if any of these occurs:

- a caller-visible effect disappears or depends only on inspecting emitted steps;
- specialization cannot recompute effects without runtime procedure values or dynamic dispatch;
- a public effect declaration would need weaker validation;
- source-map or Semantic IR provenance cannot identify the selected effect boundary; or
- the fix requires changing a workflow family, public DSL version, checkpoint identity, or result transport contract.
