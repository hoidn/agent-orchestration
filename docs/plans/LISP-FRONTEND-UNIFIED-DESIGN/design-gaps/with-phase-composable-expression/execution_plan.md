# With-Phase Composable Expression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make composed `with-phase` expressions lower correctly in the current step-backed expression positions, especially `let*` bindings and the existing `loop/recur` loop-body binding path, without changing runtime semantics or weakening shared validation.

**Architecture:** Reuse the existing `WithPhaseExpr` AST surface and the current lowering-time phase-scope machinery. Add one shared lowering normalization path in `orchestrator/workflow_lisp/lowering.py` that resolves the active phase scope, lowers the wrapped body under that scope, and exports the wrapped body's terminal outputs exactly as the surrounding `let*` and `loop/recur` binding/export logic already expects. Keep phase identity, managed write roots, diagnostics, local type rebinding, and source maps tied to the existing body-lowering rules rather than inventing a new wrapper step or runtime value.

**Tech Stack:** Python Workflow Lisp frontend, Stage 3 lowering pipeline, pytest, shared workflow validation via `compile_stage3_module(...)`

---

## Scope

- Current implementation scope: the approved `with-phase-composable-expression` design gap only.
- Primary authorities:
  - `docs/design/workflow_lisp_unified_frontend_design.md`
  - `docs/design/workflow_lisp_frontend_specification.md`
  - `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/work_instructions.md`
  - `state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/1/design-gap-architect/work_item_context.md`
  - `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/with-phase-composable-expression/implementation_architecture.md`
- Baseline constraint: current repository behavior, tests, shared validation, and implemented `ProcRef` / `bind-proc` semantics remain fixed unless this slice explicitly requires otherwise.
- This plan implements only the bounded lowering normalization needed for composed `with-phase` in the existing effectful-expression paths that already reuse step-backed export logic.
- This plan does not implement generic effectful composition for every expression family, nested `with-phase`, new phase authoring syntax, runtime closures, new runtime values, helper scripts, adapter promotion, or runtime-native effects.

## Implementation Architecture

This implementation should follow the accepted implementation architecture, but the current checkout matters more than any stale assumption about ownership. In the live code, the critical path is concentrated in `orchestrator/workflow_lisp/lowering.py`, not `compiler.py`.

### Unit 1: Shared Composed `with-phase` Lowering Helper

- Owns the normalization seam between:
  - `_lower_with_phase(...)`
  - `_lower_let_star(...)`
  - `_binding_type_for_expr(...)`
  - any helper that needs to treat `WithPhaseExpr` as transparent around an already-lowerable body
- Files:
  - Modify: `orchestrator/workflow_lisp/lowering.py`
  - Inspect only unless extraction is clearly justified: `orchestrator/workflow_lisp/phase.py`
- Stable contract:
  - resolve the active phase scope with `_resolve_active_phase_scope(...)`
  - install that scope with `_copy_context_with_phase_scope(...)`
  - lower only the wrapped body
  - return the body's steps and `_TerminalResult`
  - never create a synthetic runtime `with-phase` step
  - never derive semantic phase roots from the `let*` binding name

Suggested helper shape:

```python
def _lower_composed_with_phase(
    expr: WithPhaseExpr,
    *,
    result_type: TypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    step_name_prefix: str | None = None,
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    phase_scope = _resolve_active_phase_scope(expr, local_values=local_values)
    scoped_context = _copy_context_with_phase_scope(context, phase_scope)
    if step_name_prefix is not None:
        scoped_context = _copy_context_with_step_prefix(
            scoped_context,
            step_name_prefix=step_name_prefix,
        )
    return _lower_expression(
        TypedExpr(expr=expr.body, type_ref=result_type, ...),
        context=scoped_context,
        local_values=local_values,
    )
```

The existing `_lower_with_phase(...)` should become a thin caller of the shared helper instead of maintaining separate behavior.

### Unit 2: Binding-Type Resolution, Loop-Body Rebinding, And Export Projection

- Owns `let*` support for `WithPhaseExpr` when the wrapped body is already step-backed and exportable.
- Owns the adjacent `loop/recur` binding path when the wrapped body is already step-backed and exportable.
- Files:
  - Modify: `orchestrator/workflow_lisp/lowering.py`
- Stable contract:
  - `_binding_type_for_expr(...)` must stop rejecting `WithPhaseExpr` purely because of the wrapper class
  - binding type inference for `WithPhaseExpr` must recurse into `expr.body`
  - `_resolve_lowering_expr_type(...)` may recurse through `WithPhaseExpr` only for body families it already knows how to type from local context; it must not become the primary type source for step-backed effectful bodies in this slice
  - `_lower_let_star(...)` must lower composed `with-phase` bindings through the shared helper and then project local values from the returned terminal outputs exactly like other effectful bindings
  - `_lower_loop_body_expr(...)` must lower composed `with-phase` bindings through the same shared helper and then rebind local values and local types from the returned terminal outputs exactly like its existing step-backed binding path
  - the `loop/recur` rebinding path must take the bound local type from the same resolved `binding_type` contract already used to lower the binding, or from an equivalent shared helper output, rather than re-deriving it through a narrower generic expression-type helper
  - record/union results still become `_build_output_step_local_value(...)`
  - primitive/path results still require a terminal `"return"` output ref
  - if the wrapped body is not exportable, keep `workflow_return_not_exportable`
  - improve the rejection message so authored diagnostics say `with-phase` composition rather than only `WithPhaseExpr`
  - do not broaden `loop/recur` beyond this existing duplicated binding/export seam

### Unit 3: Private/Reusable Workflow Export Consistency

- Owns consistency between real lowering and the private-workflow export analysis helpers that already inspect step-backed bodies.
- Files:
  - Modify: `orchestrator/workflow_lisp/lowering.py`
- Stable contract:
  - `_private_workflow_binding_local_value(...)` and `_private_workflow_body_exports_step_backed_outputs(...)` must continue to treat `WithPhaseExpr` as semantically transparent around the body
  - if any helper still duplicates body-unwrapping logic, replace it with one shared path so export analysis and real lowering cannot drift again
  - preserve the existing explicit generated write-root policy when phase stdlib forms cross reusable/private boundaries
  - do not move authority for boundary validation into a new helper script, adapter, or report parser

### Unit 4: Verification Surface

- Owns focused regression tests for the selected gap and one integration-style compile check.
- Files:
  - Modify: `tests/test_workflow_lisp_lowering.py`
  - Modify: `tests/test_workflow_lisp_loop_recur.py`
  - Modify: `tests/test_workflow_lisp_phase_stdlib.py`
  - Modify: `tests/test_workflow_lisp_procedures.py`
  - Modify: `tests/test_workflow_lisp_examples.py`
  - Create: `workflows/examples/with_phase_composed_binding.orc`
- Stable contract:
  - tests must prove composed `with-phase` works where the body is already lowerable
  - tests must prove both existing step-backed binding paths (`let*` and the current `loop/recur` loop-body helper) agree on composed `with-phase` exportability and on the bound local type seen by later `match` / `recur` lowering
- tests must prove invalid compositions still fail with the existing diagnostic families
- tests must prove composed `with-phase` preserves source-map remapping so authored diagnostics still point to the wrapped binding/body site rather than only generated inner steps
- tests must include one integration-style `.orc` example that uses composed `with-phase` in a real binding position under shared validation, rather than relying only on inline fixture compilation or direct-body `with-phase` examples
- the dedicated `.orc` example should stay minimal enough to compile through the real CLI smoke path using the existing fixture extern manifests in `tests/fixtures/workflow_lisp/cli/providers.json` and `tests/fixtures/workflow_lisp/cli/prompts.json`, rather than depending on bespoke runtime setup
- tests must assert behavioral contracts and output structure, not literal prompt text or incidental formatting

## Task Checklist

### Task 1: Lock The Expected Failing Behavior In Tests

**Files:**

- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_loop_recur.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_examples.py`
- Create: `workflows/examples/with_phase_composed_binding.orc`

- [ ] Add a focused lowering test that binds a `with-phase` block inside `let*` and returns or projects the bound value later in the workflow.
- [ ] Add a focused lowering test in `tests/test_workflow_lisp_loop_recur.py` that binds a `with-phase` block inside the current `loop/recur` body binding path and proves the wrapped body exports step-backed outputs with the expected local type rebinding for later `match` / `continue` lowering.
- [ ] Add a negative lowering test where a composed `with-phase` body still is not step-backed/exportable and must fail under `workflow_return_not_exportable`.
- [ ] Add a focused source-map regression that forces a shared-validation or lowering diagnostic through a composed `with-phase` body and proves the reported `span` / `form_path` remap lands on the authored binding or wrapped body site.
- [ ] Add a reusable/private-workflow regression that proves a body or binding wrapped in `with-phase` still exports step-backed outputs under the existing private-workflow rules.
- [ ] Add a phase-stdlib regression that proves composed `with-phase` keeps explicit generated write-root inputs and deterministic phase-root behavior when reusable boundaries are involved.
- [ ] Add a dedicated example workflow under `workflows/examples/` whose authored `let*` or loop binding wraps a step-backed body in `with-phase`, and add a matching compile test in `tests/test_workflow_lisp_examples.py` that runs `compile_stage3_module(..., validate_shared=True)` against that example.

Suggested test names:

- `test_compile_stage3_module_lowers_with_phase_let_binding_to_step_backed_outputs`
- `test_lowering_loop_recur_with_composed_with_phase_binding_exports_step_backed_outputs`
- `test_compile_stage3_module_rejects_non_exportable_composed_with_phase_binding`
- `test_compile_stage3_module_remaps_composed_with_phase_diagnostic_to_authored_binding_site`
- `test_private_workflow_with_phase_binding_exports_step_backed_outputs`
- `test_reusable_phase_state_with_composed_with_phase_preserves_generated_write_root_inputs`
- `test_with_phase_composed_binding_orc_compiles_to_typed_phase_stack`

Suggested positive fixture shape:

```lisp
(defworkflow entry
  ((phase-ctx ImplementationAttemptPhaseCtx)
   (inputs ImplementationAttemptInputs))
  -> ImplementationAttemptSurfaceResult
  (let* ((phase-result
           (with-phase phase-ctx implementation
             (let* ((attempt
                      (provider-result providers.execute ... :returns ImplementationAttempt)))
               (match attempt
                 ((COMPLETED completed) (record ImplementationAttemptSurfaceResult ...))
                 ((BLOCKED blocked) (record ImplementationAttemptSurfaceResult ...)))))))
    phase-result))
```

Suggested negative fixture shape:

```lisp
(let* ((bad
         (with-phase phase-ctx implementation
           inputs.some_non_step_backed_field)))
  bad)
```

Suggested loop/recur fixture shape:

```lisp
(defworkflow entry
  ((phase-ctx ImplementationAttemptPhaseCtx)
   (seed AttemptLoopState))
  -> ImplementationAttemptSurfaceResult
  (loop/recur :max 3 :state seed
    (fn (state)
      (let* ((phase-result
               (with-phase phase-ctx implementation
                 (provider-result providers.execute ... :returns ImplementationAttempt))))
        (match phase-result
          ((COMPLETED completed)
           (done (record ImplementationAttemptSurfaceResult ...)))
          ((BLOCKED blocked)
           (continue (record AttemptLoopState ...))))))))
```

Suggested example-workflow shape:

```lisp
(defworkflow run-with-phase-composed-binding
  ((phase-ctx ImplementationAttemptPhaseCtx)
   (report_path WorkReport))
  -> ImplementationAttemptSurfaceResult
  (let* ((phase-result
           (with-phase phase-ctx implementation
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs (report_path)
               :returns ImplementationAttemptSurfaceResult))))
    phase-result))
```

**Blocking verification after Task 1:**

- [ ] If any new tests are added or renamed, run:
  - `pytest --collect-only tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_loop_recur.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_examples.py -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_lowers_with_phase_let_binding_to_step_backed_outputs -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_loop_recur.py::test_lowering_loop_recur_with_composed_with_phase_binding_exports_step_backed_outputs -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_rejects_non_exportable_composed_with_phase_binding -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_remaps_composed_with_phase_diagnostic_to_authored_binding_site -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_procedures.py::test_private_workflow_with_phase_binding_exports_step_backed_outputs -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_phase_stdlib.py::test_reusable_phase_state_with_composed_with_phase_preserves_generated_write_root_inputs -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_examples.py::test_with_phase_composed_binding_orc_compiles_to_typed_phase_stack -q`
- [ ] Record the dedicated example workflow's entrypoint name in the test and fixture so Task 4 can compile it through `python -m orchestrator compile ...` without guessing.

Expected before implementation: the new positive tests fail because `WithPhaseExpr` is still rejected or under-typed in composed binding lowering paths, including `let*`, the duplicated `loop/recur` helper, private/reusable export checks, and the dedicated example compile, where local type rebinding is still sourced from `_resolve_lowering_expr_type(...)` instead of the actual lowered binding contract. The new source-map regression should also fail until the composed path preserves authored remap/origin data. Existing nested-scope and invalid-phase diagnostics should remain unchanged.

### Task 2: Add The Shared Composed `with-phase` Lowering Path

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`

- [ ] Introduce one shared helper for composed `with-phase` lowering that resolves phase scope, copies the lowering context, optionally applies a child `step_name_prefix`, and lowers `expr.body`.
- [ ] Refactor `_lower_with_phase(...)` to use that shared helper so the direct-body path and composed path cannot diverge.
- [ ] Extend `_binding_type_for_expr(...)` so `WithPhaseExpr` delegates type resolution to its wrapped body.
- [ ] Extend `_resolve_lowering_expr_type(...)` so `WithPhaseExpr` delegates local type resolution to its wrapped body only where the wrapped body already has a lowering-time type path; do not rely on this helper to invent generic type resolution for step-backed effectful forms.
- [ ] Update `_lower_let_star(...)` so effectful `WithPhaseExpr` bindings use the shared helper and export local values from the resulting terminal outputs exactly like other effectful bindings.
- [ ] Update `_lower_loop_body_expr(...)` so effectful `WithPhaseExpr` bindings use the shared helper and rebind local values/local types exactly like its existing step-backed binding path.
- [ ] Make the `loop/recur` local-type rebinding path reuse the already-resolved `binding_type` for composed `with-phase` bindings, or an equivalently shared binding-analysis result, so wrapped `provider-result` / `command-result` / `call` bodies do not depend on unrelated generic expression-type coverage.
- [ ] Keep deterministic phase roots anchored to resolved context roots plus authored phase name. Do not introduce binding-name-based semantic roots.
- [ ] Preserve existing origin-map/source-map plumbing so diagnostics raised from inner provider/command/call lowering or shared validation can still remap to the composed `with-phase` binding/body span and form path.
- [ ] Keep existing error families for invalid `PhaseCtx`, generic phase roots, and legacy-bridge misuse.

Implementation guardrails:

- Do not add a new AST node.
- Do not add runtime `with-phase` values.
- Do not add a second lowering path that bypasses `_lower_expression(...)`.
- Do not let `with-phase` fabricate inline values for bodies that were not already exportable.
- Do not broaden `_resolve_lowering_expr_type(...)` into a second effectful type-inference system just to make the loop fixture pass.

**Blocking verification after Task 2:**

- [ ] Run:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_lowers_with_phase_let_binding_to_step_backed_outputs -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_loop_recur.py::test_lowering_loop_recur_with_composed_with_phase_binding_exports_step_backed_outputs -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_rejects_non_exportable_composed_with_phase_binding -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_remaps_composed_with_phase_diagnostic_to_authored_binding_site -q`
- [ ] Re-run the existing direct `with-phase` lowering regression:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_lowers_phase_translation_fixture_with_phase_scoped_bundle_path -q`
- [ ] Re-run the existing nested-scope guard:
  - `pytest tests/test_workflow_lisp_phase_translation.py::test_typecheck_rejects_nested_with_phase -q`
- [ ] Re-run one existing loop/recur lowering regression from the dedicated module so shared loop-body changes are proven against baseline behavior:
  - `pytest tests/test_workflow_lisp_loop_recur.py::test_lowering_loop_recur_allows_letstar_inside_body -q`

Expected after Task 2: the positive `let*` and `loop/recur` lowering tests pass, the loop fixture gets its later `match` / `recur` local type from the same binding contract used to lower the wrapped step-backed body, the negative lowering test still fails with `workflow_return_not_exportable`, the new source-map regression proves the composed path remaps diagnostics to the authored binding/body site, the existing direct `with-phase` path still lowers the phase-scoped bundle/output fixture unchanged, and nested `with-phase` rejection is unchanged.

### Task 3: Unify Private-Workflow Exportability With Real Lowering

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] Reuse the same composed-`with-phase` logic in the private/reusable export-analysis helpers so they no longer answer a different question from real lowering.
- [ ] Keep `WithPhaseExpr` transparent around the wrapped body in `_private_workflow_binding_local_value(...)` and `_private_workflow_body_exports_step_backed_outputs(...)`.
- [ ] If helper duplication remains after the narrowing fix, extract the minimum shared utility inside `lowering.py`; do not move logic into a new module unless the extraction materially reduces drift risk.
- [ ] Confirm reusable/private workflow boundaries still surface explicit generated relpath inputs for managed write roots when phase stdlib operations require them.
- [ ] Keep source-map ownership on the inner provider/command/call/loop steps and preserve authored spans and form paths in failures tied to the composed binding site.

**Blocking verification after Task 3:**

- [ ] Run:
  - `pytest tests/test_workflow_lisp_procedures.py::test_private_workflow_with_phase_binding_exports_step_backed_outputs -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_phase_stdlib.py::test_reusable_phase_state_with_composed_with_phase_preserves_generated_write_root_inputs -q`
- [ ] Re-run the composed source-map selector after the private/reusable helper changes to guard against provenance drift:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_remaps_composed_with_phase_diagnostic_to_authored_binding_site -q`
- [ ] Re-run one existing phase stdlib/shared-validation check for regression coverage:
  - `pytest tests/test_workflow_lisp_phase_stdlib.py::test_shared_validation_accepts_run_provider_phase_and_produce_one_of -q`

Expected after Task 3: private/reusable workflow checks agree with real lowering, managed write-root behavior remains explicit and deterministic, and the provenance/remap path still points diagnostics at the authored composed `with-phase` site after the export-analysis alignment.

### Task 4: Run The Focused Regression And Integration Proof

**Files:**

- No additional maintained source files; this task validates the changed lowering contract, including the example workflow and test added in Task 1.

- [ ] Run the focused module subset:
  - `pytest tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_loop_recur.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_phase_stdlib.py -k "with_phase or loop_recur or phase_state or shared_validation_accepts_run_provider_phase_and_produce_one_of" -q`
- [ ] Run the dedicated source-map regression explicitly so provenance coverage does not get lost inside a broad keyword selector:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_remaps_composed_with_phase_diagnostic_to_authored_binding_site -q`
- [ ] Re-run the exact direct `with-phase` lowering regression that exercises the refactored top-level path:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_lowers_phase_translation_fixture_with_phase_scoped_bundle_path -q`
- [ ] Re-run the new composed loop/recur regression explicitly from the dedicated loop module:
  - `pytest tests/test_workflow_lisp_loop_recur.py::test_lowering_loop_recur_with_composed_with_phase_binding_exports_step_backed_outputs -q`
- [ ] Re-run one existing loop/recur lowering regression from the dedicated module so additive regressions in ordinary body lowering, result projection, and routing are visible:
  - `pytest tests/test_workflow_lisp_loop_recur.py::test_loop_recur_supports_if_routing_between_continue_and_done -q`
- [ ] Run the direct phase translation guard subset:
  - `pytest tests/test_workflow_lisp_phase_translation.py -k "nested_with_phase or invalid_phase_context_record or non_implementation_phase_name_for_bounded_slice" -q`
- [ ] Run the dedicated integration-style composed-`with-phase` example compile under shared validation:
  - `pytest tests/test_workflow_lisp_examples.py::test_with_phase_composed_binding_orc_compiles_to_typed_phase_stack -q`
- [ ] Run one repo-policy CLI smoke against the new example workflow so the frontend change is proven through the real orchestrator compile surface, not only through direct Python compilation helpers:
  - `python -m orchestrator compile workflows/examples/with_phase_composed_binding.orc --entry-workflow run-with-phase-composed-binding --provider-externs-file tests/fixtures/workflow_lisp/cli/providers.json --prompt-externs-file tests/fixtures/workflow_lisp/cli/prompts.json --emit-debug-yaml .orchestrate/tmp/with-phase-composed-binding-smoke/expanded.debug.yaml --emit-core-ast .orchestrate/tmp/with-phase-composed-binding-smoke/core_workflow_ast.json --emit-semantic-ir .orchestrate/tmp/with-phase-composed-binding-smoke/semantic_ir.json --emit-source-map .orchestrate/tmp/with-phase-composed-binding-smoke/source_map.json`
- [ ] Re-run one existing real-example compile so the narrowed gap still proves additive compatibility with the current example suite:
  - `pytest tests/test_workflow_lisp_examples.py::test_kiss_backlog_item_orc_compiles_to_typed_phase_stack -q`
- [ ] If any selector above is too broad because final test names differ, keep the commands narrow and update them in the implementation summary rather than dropping verification.

Expected outcome:

- composed `with-phase` bindings lower successfully when the wrapped body is already step-backed and exportable
- the adjacent `loop/recur` binding helper matches `let*` on composed `with-phase` exportability and takes its later local type rebinding from the same resolved binding contract
- the dedicated `loop/recur` regression module still passes its baseline body-lowering and routing checks after the shared loop-body change
- invalid composed bodies still fail under existing diagnostic families
- composed `with-phase` diagnostics still remap to the authored binding/body span and form path
- direct `with-phase` body lowering remains unchanged after the shared-helper refactor
- nested `with-phase` remains rejected
- reusable/private write-root behavior stays explicit
- the dedicated `.orc` example that uses composed `with-phase` in a real binding position compiles under shared validation
- the same dedicated `.orc` example also compiles through `python -m orchestrator compile ...`, emitting debug/core/source-map artifacts through the public CLI path
- no new command adapter, helper script, or runtime effect appears

## Explicit Non-Goals

- Do not implement generic effectful-composition completion for all expression families.
- Do not add nested `with-phase` support.
- Do not redesign `PhaseCtx`, `phase-target`, provider execution, pointer authority, state layout, or runtime observability.
- Do not add helper scripts, command adapters, inline shell/Python glue, or runtime-native effects to make composition work.
- Do not reopen already implemented `ProcRef` / `bind-proc` behavior or unrelated Workflow Lisp refactors.

## Implementation Notes

- Treat `workflow_return_not_exportable` as the correct error class for non-exportable composed bodies. The required change is message quality and wrapper transparency, not a new diagnostic taxonomy.
- Prefer editing only `orchestrator/workflow_lisp/lowering.py` unless test evidence proves a narrower helper extraction in `phase.py` is necessary.
- Keep the example workflow narrow enough that the recorded verification can include both `compile_stage3_module(..., validate_shared=True)` and the public `python -m orchestrator compile ...` smoke using the existing CLI fixture extern manifests.
- Record in the implementation summary which exact test selectors were added and which verification commands passed, including the dedicated composed-`with-phase` example compile, the public CLI compile smoke, and any `--collect-only` run required by added or renamed tests.
