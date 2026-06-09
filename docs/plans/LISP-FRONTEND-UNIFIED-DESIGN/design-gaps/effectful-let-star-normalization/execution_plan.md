# Effectful Let-Star Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the bounded Stage 3 normalization that lets sequential `let*` bindings share one lowering/export contract across ordinary workflow bodies, loop-body `let*`, and private/generated workflow exportability, including effectful binding-position `match` over already step-backed subjects.

**Architecture:** Keep the change inside `orchestrator/workflow_lisp/lowering.py`. Introduce one shared binding-normalization helper that classifies a binding as inline or step-backed, resolves its result type through one recursive contract, lowers supported step-backed bindings with deterministic step names, and projects one local value shape for later bindings. Reuse that helper from `_lower_let_star(...)` and `_lower_loop_body_expr(...)`, and mirror the same acceptance/local-projection rules in private-workflow exportability so the three surfaces cannot drift again.

**Tech Stack:** Python 3, Workflow Lisp frontend lowering pipeline, shared validation via `compile_stage3_module(...)`, `pytest`, and one public `python -m orchestrator compile ...` smoke check

---

## Scope

- Current implementation scope: the approved `effectful-let-star-normalization` design gap only.
- Primary authorities:
  - `docs/design/workflow_lisp_unified_frontend_design.md`
  - `docs/design/workflow_lisp_frontend_specification.md`
  - `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/work_instructions.md`
  - `state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/6/design-gap-architect/work_item_context.md`
  - `state/LISP-FRONTEND-UNIFIED-DESIGN/progress_ledger.json`
  - `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/effectful-let-star-normalization/implementation_architecture.md`
- Baseline constraint: current repository behavior, tests, shared validation, and accepted implemented `ProcRef` / `bind-proc` semantics remain fixed unless this slice explicitly requires otherwise.
- The consumed progress ledger currently records no events, so this slice must provide its own complete regression proof rather than assuming partially landed work elsewhere.
- This plan implements only the bounded sequential binding normalization described in the approved architecture:
  - one shared Stage 3 binding-normalization seam for `let*`;
  - recursive binding result-type resolution for already supported composed bindings;
  - binding-position `match` lowering when the subject is already step-backed;
  - parity between ordinary `let*`, loop-body `let*`, and private/generated workflow exportability checks;
  - one realistic compile-style example for sequential effectful bindings.
- This plan does not implement `let*` syntax redesign, typechecker redesign, new runtime nodes, runtime closures, dynamic dispatch, write-root policy redesign, shared runtime/provider/command semantic changes, or Core/Semantic/Executable IR redesign.

## Current Checkout Facts

- `_lower_let_star(...)` in `orchestrator/workflow_lisp/lowering.py` still hard-codes two separate branches for inline bindings versus effectful bindings and contains a special match-after-binding path.
- `_lower_loop_body_expr(...)` reimplements a similar inline/effectful split for nested loop-body `let*`, so ordinary lowering and loop lowering can already drift.
- `_binding_type_for_expr(...)` is still a closed allowlist. It unwraps `WithPhaseExpr`, handles known step-backed forms, and otherwise fails with `Stage 3 lowering does not support let* binding ...`.
- `_resolve_lowering_expr_type(...)` already knows how to recurse through `MatchExpr`, `IfExpr`, `LetStarExpr`, `LoopRecurExpr`, and `WithPhaseExpr`, but that richer type information is not the authority for sequential binding lowering yet.
- `_lower_expression(...)` still has no generic `MatchExpr` branch, so effectful `match` lowering is currently available only through `_lower_match_expr(...)` when `_lower_let_star(...)` recognizes the narrow body-after-binding shape.
- `_lower_effectful_binding_expr(...)` already reuses `_lower_composed_with_phase(...)` and the ordinary lowering path for many step-backed expression families.
- `_binding_local_value_from_terminal(...)`, `_build_output_step_local_value(...)`, and `_match_arm_local_values(...)` already provide the local-value projection machinery needed for structured step-backed outputs.
- `_private_workflow_binding_local_value(...)` and `_private_workflow_body_exports_step_backed_outputs(...)` still approximate binding exportability with narrower rules than real lowering, especially for composed `let*` and binding-position `match`.
- Existing adjacent regressions already cover composed `with-phase`, generic effectful `match` arms, same-file record call bindings, and private-workflow effectful match arms. This slice must keep those paths green.

## File Map

**Primary implementation file**
- Modify: `orchestrator/workflow_lisp/lowering.py`

**Primary test files**
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_loop_recur.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_examples.py`

**Example workflow**
- Create: `workflows/examples/effectful_let_star_normalization.orc`

**Inspect or verify only unless narrow diagnostic alignment is required**
- Inspect: `orchestrator/workflow_lisp/typecheck.py`
- Verify: `tests/test_workflow_lisp_resource_stdlib.py`

## Required Behaviors To Prove

- A sequential `let*` can bind an effectful step-backed value, then bind a `MatchExpr` over that value, then bind a later effectful expression that consumes fields from the match result through the ordinary local-value projection model.
- The same binding contract works when inline, pure, compile-time, and step-backed bindings are mixed in authored order; compile-time-only bindings such as `proc-ref` and `bind-proc` remain erased before runtime artifacts.
- Loop-body `let*` reuses the same binding normalization contract, so a loop body can sequence an effectful binding and then a binding-position `match` without bespoke loop-only projection logic.
- Private/generated workflow exportability accepts the same composed binding shapes that real lowering accepts and still rejects non-exportable leaves under the existing diagnostic family.
- Binding-position `match` only lowers when its subject already resolves to a step-backed structured value; unsupported subjects still fail deterministically with source-mapped diagnostics.
- Unsupported composed binding result types still fail through the shared binding-result helper with authored binding-site diagnostics rather than helper-internal leakage.
- Compile-time-only procedure values stay erased from runtime artifacts, and any sequential binding shape that would transport `proc-ref` / `bind-proc` values into runtime state or workflow results still fails under the existing compile-time/runtime boundary diagnostic family.
- Deterministic generated step ids, hidden-input accumulation, managed write-root policy, and source-map origin tracking remain intact.
- Shared command boundaries remain explicit: sequential normalization preserves `command-result` and certified-adapter lowering without introducing wrapper scripts, implicit adapter promotion, or hidden bundle writes.
- At least one checked-in `.orc` example compiles under both `compile_stage3_module(..., validate_shared=True)` and `python -m orchestrator compile ...`.

## Implementation Architecture

This slice should follow the approved implementation architecture, but the live ownership stays narrow: the missing seam is concentrated in `orchestrator/workflow_lisp/lowering.py`.

### Unit 1: Shared Sequential Binding Normalization Contract

- Owns the one lowering-only helper that turns one authored `let*` binding into either an inline local binding or a step-backed binding result.
- File:
  - Modify: `orchestrator/workflow_lisp/lowering.py`
- Stable contract:
  - inline bindings remain the existing pure/compile-time shapes:
    - `NameExpr`
    - `FieldAccessExpr`
    - `LiteralExpr`
    - `RecordExpr`
    - `ProcRefLiteralExpr`
    - `BindProcExpr`
  - step-backed bindings return one shared result bundle:
    - resolved `binding_type`
    - emitted `steps`
    - `terminal`
    - projected `local_value`
    - any `hidden_inputs` carried by the terminal
  - result-type resolution must stop being a closed allowlist and instead recurse through already supported composed expression shapes, especially:
    - `WithPhaseExpr`
    - `MatchExpr`
    - `IfExpr`
    - nested `LetStarExpr`
    - `LoopRecurExpr`
    - workflow/procedure calls
    - current stdlib result expressions
  - compile-time-only values stay inline only; the helper must not emit any runtime artifact that serializes a `ProcRef`, `bind-proc` result, or other compile-time authoring value.

Suggested helper shape:

```python
@dataclass(frozen=True)
class _NormalizedBindingResult:
    binding_type: TypeRef
    emitted_steps: list[dict[str, Any]]
    terminal: _TerminalResult | None
    local_value: Any

def _normalize_let_binding(
    binding_name: str,
    binding_expr: Any,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    step_name_prefix: str,
    lower_step_backed: Callable[[Any, TypeRef, str], tuple[list[dict[str, Any]], _TerminalResult]],
) -> _NormalizedBindingResult:
    ...
```

- Do not introduce a new public module or runtime node. Keep the helper private to `lowering.py`.

### Unit 2: Binding-Position `match` And `let*` Consumers

- Owns ordinary `let*` lowering, loop-body `let*` lowering, and the minimal subject-terminal plumbing needed for binding-position `match`.
- File:
  - Modify: `orchestrator/workflow_lisp/lowering.py`
- Stable contract:
  - `_lower_let_star(...)` consumes the shared binding-normalization helper for every binding instead of carrying a bespoke inline/effectful split.
  - `_lower_loop_body_expr(...)` consumes the same helper for its nested `let*` branch so loop-body sequencing cannot drift from ordinary sequencing.
  - binding-position `match` must no longer depend on "the body immediately after the binding is a match on that binding name" as the only lowering path.
  - later bindings and final bodies must keep seeing structured local refs through `_build_output_step_local_value(...)` and related helpers rather than a second local-value shape.
  - hidden inputs from each normalized binding must be merged in authored order with downstream terminal hidden inputs.
  - deterministic step-name allocation must continue to derive from lexical binding order and binding names.

Required implementation direction:

- Add one tiny helper that resolves whether a `MatchExpr` subject already corresponds to a step-backed structured terminal available in `local_values`.
- Either:
  - add a narrow `MatchExpr` branch to `_lower_effectful_binding_expr(...)` / `_lower_expression(...)`, or
  - add a dedicated binding-position match lowerer reused by the binding-normalization helper.
- In either case, the required outcome is the same: a `MatchExpr` used as a `let*` binding lowers through the existing `_lower_match_expr(...)` branch machinery when its subject already has step-backed local refs, and still rejects otherwise.
- Keep the previously landed `with-phase` and generic effectful match-arm slices authoritative. This slice may reuse them, but must not replace their step shapes or runtime authority rules.

Suggested match-subject helper shape:

```python
def _binding_terminal_for_match_subject(
    subject: Any,
    *,
    local_values: Mapping[str, Any],
) -> _TerminalResult | None:
    resolved = _resolve_inline_expr_value(subject, local_values=local_values)
    return _binding_terminal_for_inline_match(resolved)
```

### Unit 3: Private/Generated Workflow Exportability Parity

- Owns agreement between real lowering and private/generated workflow body export checks for composed bindings.
- File:
  - Modify: `orchestrator/workflow_lisp/lowering.py`
- Stable contract:
  - `_private_workflow_binding_local_value(...)` must stop using a narrower one-off approximation for composed bindings.
  - composed `let*`, binding-position `match`, and `with-phase` bindings must reuse the same acceptance and projected local-value rules that real lowering uses.
  - `_private_workflow_body_exports_step_backed_outputs(...)` and `_match_outputs_are_step_backed(...)` must continue to be the authority for "does this body export step-backed values?", but they should consume the same branch-local binding model and binding result-type rules as real lowering.
  - keep recursive procedure guards, managed write-root policy, and existing diagnostic codes intact.

Recommended direction:

```python
binding_type = _binding_result_type_for_expr(binding_expr, context=context)
if _private_binding_expr_exports_step_backed_outputs(...):
    return _private_workflow_local_value_for_type(
        binding_type,
        step_name=binding_name,
        ...
    )
```

- Do not add a looser fallback that guesses runtime behavior from prompt text, rendered plans, pointer files, or reports. Structured local values and validated return types remain authority.

### Unit 4: Verification Surface

- Owns focused regressions, one realistic example workflow, and one public CLI compile smoke.
- Files:
  - Modify: `tests/test_workflow_lisp_lowering.py`
  - Modify: `tests/test_workflow_lisp_loop_recur.py`
  - Modify: `tests/test_workflow_lisp_procedures.py`
  - Modify: `tests/test_workflow_lisp_examples.py`
  - Create: `workflows/examples/effectful_let_star_normalization.orc`
- Stable contract:
  - tests assert lowering behavior, exported structure, and diagnostics, not literal prompt text
  - at least one loop-body regression proves the shared helper is actually shared
  - at least one private-workflow regression proves exportability now matches real lowering
  - negative tests cover the required rejection surfaces:
    - non-step-backed binding-position `match` subjects
    - unresolved composed binding result types
    - compile-time-only procedure values escaping into runtime results
    - binding-site diagnostic remaps for non-exportable composed bodies
  - verification includes explicit command-boundary evidence through at least one existing `command-result` or certified-adapter regression selector
  - the checked-in example is provider-only so the CLI smoke needs only the existing provider/prompt extern manifests

## Task Checklist

### Task 1: Lock The Missing Sequential-Binding Behavior In Tests

**Files:**

- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_loop_recur.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_examples.py`
- Create: `workflows/examples/effectful_let_star_normalization.orc`

- [ ] Add a focused lowering test where a `let*` sequence binds:
  - one step-backed union result from `provider-result`,
  - one binding-position `match` over that union that returns a step-backed record in each arm,
  - one later effectful binding that consumes a field from the match result.
- [ ] Add a second lowering test where the binding-position `match` returns a step-backed result and the final workflow body reads that result directly, proving later body projection also flows through the same contract.
- [ ] Add a negative lowering test where a binding-position `match` subject is not step-backed, and assert the existing source-mapped binding diagnostic points at the authored binding expression.
- [ ] Add a negative lowering test where a composed binding result type still cannot be resolved by the shared binding-result helper, and assert the failure stays form-specific instead of falling back to a raw helper/internal-only error.
- [ ] Add a negative lowering test where a sequential binding would let a compile-time-only `proc-ref` or `bind-proc` value escape into a runtime result path, and assert the existing compile-time/runtime boundary diagnostic family still fires at the authored site.
- [ ] Add a negative lowering/shared-validation test where a binding-position `match` ultimately exports at least one non-step-backed leaf such as a literal status field, and assert both `workflow_return_not_exportable` and authored binding-site remap coverage.
- [ ] Add a loop-body regression where `loop/recur` contains a nested `let*` whose second binding is a binding-position `match` over a previously lowered loop-local step-backed value.
- [ ] Add a private-workflow regression showing a `:lowering private-workflow` procedure with sequential effectful bindings, including binding-position `match`, compiles and emits the generated private workflow.
- [ ] Add a checked-in example workflow under `workflows/examples/` that demonstrates sequential effectful bindings in one realistic but bounded shape, and add a matching `tests/test_workflow_lisp_examples.py` compile test that runs `compile_stage3_module(..., validate_shared=True)`.
- [ ] Keep the checked-in example minimal and provider-only; reuse:
  - `tests/fixtures/workflow_lisp/cli/providers.json`
  - `tests/fixtures/workflow_lisp/cli/prompts.json`

Suggested test names:

- `test_compile_stage3_module_lowers_effectful_let_star_match_binding_sequence`
- `test_compile_stage3_module_lowers_effectful_let_star_match_binding_follow_on_step`
- `test_compile_stage3_module_rejects_effectful_let_star_match_binding_without_step_backed_subject`
- `test_compile_stage3_module_rejects_effectful_let_star_unresolved_composed_binding_type`
- `test_compile_stage3_module_rejects_effectful_let_star_runtime_proc_ref_escape`
- `test_compile_stage3_module_rejects_non_exportable_effectful_match_binding_result`
- `test_lowering_loop_recur_normalizes_effectful_match_binding_sequence`
- `test_private_workflow_effectful_let_star_bindings_export_step_backed_outputs`
- `test_effectful_let_star_normalization_orc_compiles_with_shared_validation`

Suggested positive fixture shape:

```lisp
(defworkflow provider-attempt
  ((report_path WorkReport))
  -> AttemptReport
  (let* ((attempt
           (provider-result providers.execute
             :prompt prompts.implementation.execute
             :inputs (report_path)
             :returns ImplementationState))
         (summary
           (match attempt
             ((COMPLETED completed)
              (provider-result providers.execute
                :prompt prompts.implementation.execute
                :inputs (completed.execution_report)
                :returns AttemptReport))
             ((BLOCKED blocked)
              (provider-result providers.execute
                :prompt prompts.implementation.execute
                :inputs (blocked.progress_report)
                :returns AttemptReport))))
         (final
           (provider-result providers.execute
             :prompt prompts.implementation.execute
             :inputs (summary.report)
             :returns AttemptReport)))
    final))
```

Suggested loop-body fixture shape:

```lisp
(loop/recur :max 2 :state attempt
  (fn (state)
    (let* ((next-attempt
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs (state.report)
               :returns ImplementationState))
           (summary
             (match next-attempt
               ((COMPLETED completed)
                (provider-result providers.execute
                  :prompt prompts.implementation.execute
                  :inputs (completed.execution_report)
                  :returns AttemptReport))
               ((BLOCKED blocked)
                (provider-result providers.execute
                  :prompt prompts.implementation.execute
                  :inputs (blocked.progress_report)
                  :returns AttemptReport)))))
      (done summary))))
```

**Blocking verification after Task 1:**

- [ ] If any tests are added or renamed, run:
  - `pytest --collect-only tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_loop_recur.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_examples.py -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_lowers_effectful_let_star_match_binding_sequence -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_lowers_effectful_let_star_match_binding_follow_on_step -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_rejects_effectful_let_star_match_binding_without_step_backed_subject -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_rejects_effectful_let_star_unresolved_composed_binding_type -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_rejects_effectful_let_star_runtime_proc_ref_escape -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_rejects_non_exportable_effectful_match_binding_result -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_loop_recur.py::test_lowering_loop_recur_normalizes_effectful_match_binding_sequence -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_procedures.py::test_private_workflow_effectful_let_star_bindings_export_step_backed_outputs -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_examples.py::test_effectful_let_star_normalization_orc_compiles_with_shared_validation -q`

Expected before implementation: the new positive tests fail because the current binding seam still rejects binding-position `MatchExpr` and ordinary versus loop-body/private-workflow binding acceptance are still split across separate approximations; the new negative/remap tests should expose the current missing binding-site rejection coverage explicitly.

### Task 2: Implement The Shared Binding-Normalization And Result-Type Helpers

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`
- Inspect only unless a narrow diagnostic mismatch appears: `orchestrator/workflow_lisp/typecheck.py`

- [ ] Add one private binding-normalization helper that returns the resolved binding type, emitted steps, terminal, and projected local value for one binding.
- [ ] Replace the closed `_binding_type_for_expr(...)` logic with one recursive helper that can resolve already-supported composed binding result types without node-class allowlist growth.
- [ ] Reuse `_resolve_lowering_expr_type(...)` and existing typed return-type authorities wherever possible instead of re-encoding type joins by hand.
- [ ] Keep inline bindings on the existing pure/compile-time path, including `ResolvedProcRefValue` handling for `proc-ref` and `bind-proc`.
- [ ] Add one tiny helper that resolves a `MatchExpr` subject terminal from already available step-backed local refs so binding-position `match` can lower without depending on the old immediate-body special case.
- [ ] Preserve deterministic step-name generation from lexical binding order and binding names.
- [ ] Preserve managed write-root determinism, explicit command/provider boundaries, hidden-input accumulation, and source-map origin tracking.

Implementation guardrails:

- Do not add a new AST node.
- Do not add a second runtime branch representation.
- Do not weaken shared validation or pointer authority.
- Do not serialize compile-time procedure values into runtime outputs, state, or local-value projections.

**Blocking verification after Task 2:**

- [ ] Re-run the new focused lowering tests:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_lowers_effectful_let_star_match_binding_sequence -q`
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_lowers_effectful_let_star_match_binding_follow_on_step -q`
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_rejects_effectful_let_star_match_binding_without_step_backed_subject -q`
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_rejects_effectful_let_star_unresolved_composed_binding_type -q`
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_rejects_effectful_let_star_runtime_proc_ref_escape -q`
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_rejects_non_exportable_effectful_match_binding_result -q`
- [ ] Re-run one existing generic-match regression to prove the shared match machinery stays compatible:
  - `pytest tests/test_workflow_lisp_lowering.py::test_lower_workflow_definitions_supports_generic_match_outputs -q`
- [ ] Re-run one existing composed-with-phase regression to prove the binding helper still treats the wrapper as semantically transparent:
  - `pytest tests/test_workflow_lisp_examples.py::test_with_phase_composed_binding_orc_compiles_to_typed_phase_stack -q`
- [ ] Re-run one existing shared-validation remap regression to prove composed-binding failures still point back to authored surfaces:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_remaps_shared_validation_failures -q`
- [ ] Re-run one existing direct `command-result` regression to prove the shared binding seam did not add hidden bundle writes or change command-boundary ownership:
  - `pytest tests/test_workflow_lisp_procedures.py::test_direct_command_result_procedure_effects_do_not_require_hidden_bundle_writes -q`

Expected after Task 2: ordinary `let*` can sequence effectful bindings through one shared contract, binding-position `match` lowers when its subject already resolves to step-backed local refs, and non-exportable leaves still fail under `workflow_return_not_exportable`.

### Task 3: Make Loop-Body `let*` And Private-Workflow Exportability Consume The Same Contract

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`

- [ ] Refactor `_lower_loop_body_expr(...)` so its nested `let*` branch consumes the shared binding-normalization helper instead of maintaining a second inline/effectful split.
- [ ] Update `_private_workflow_binding_local_value(...)` so composed bindings use the same acceptance and local-value projection rules as real lowering.
- [ ] Extend private/generated workflow analysis to accept binding-position `match` only when its subject is already step-backed and each branch exports step-backed outputs through the existing authority checks.
- [ ] Preserve recursive procedure guards, existing `workflow_return_not_exportable` / `proc_private_workflow_boundary_invalid` diagnostic families, and caller-owned managed write-root behavior.
- [ ] If needed, extract one tiny shared helper for branch-local binding maps or step-backed local-value construction rather than copying logic between lowering and exportability.

**Blocking verification after Task 3:**

- [ ] Re-run:
  - `pytest tests/test_workflow_lisp_loop_recur.py::test_lowering_loop_recur_normalizes_effectful_match_binding_sequence -q`
  - `pytest tests/test_workflow_lisp_procedures.py::test_private_workflow_effectful_let_star_bindings_export_step_backed_outputs -q`
- [ ] Re-run adjacent existing regressions:
  - `pytest tests/test_workflow_lisp_loop_recur.py::test_lowering_loop_recur_with_composed_with_phase_binding_exports_step_backed_outputs -q`
  - `pytest tests/test_workflow_lisp_procedures.py::test_private_workflow_effectful_match_arms_export_step_backed_outputs -q`
  - `pytest tests/test_workflow_lisp_examples.py::test_effectful_match_arm_normalization_orc_compiles_with_shared_validation -q`
- [ ] Re-run one existing helper-provenance/shared-validation regression if Task 3 touches exportability remap paths:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_renders_helper_provenance_notes_for_shared_validation_errors -q`

Expected after Task 3: ordinary `let*`, loop-body `let*`, and private/generated workflow exportability all accept the same bounded set of step-backed composed bindings, and adjacent effectful-composition slices remain additive.

### Task 4: Run The Focused Regression And End-To-End Compile Proof

**Files:**

- No additional maintained source files; this task validates the changed lowering contract and the checked-in example workflow.

- [ ] Run the focused regression subset:
  - `pytest tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_loop_recur.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_examples.py -k "effectful_let_star or generic_match_outputs or with_phase_composed_binding or effectful_match_arm_normalization or private_workflow_effectful_match_arms or loop_recur_normalizes_effectful_match_binding_sequence or remaps_shared_validation" -q`
- [ ] Re-run the new shared-validation example compile explicitly:
  - `pytest tests/test_workflow_lisp_examples.py::test_effectful_let_star_normalization_orc_compiles_with_shared_validation -q`
- [ ] Re-run one certified-adapter regression so command-adapter lowering remains explicitly covered alongside provider-only example compilation:
  - `pytest tests/test_workflow_lisp_resource_stdlib.py::test_lowering_resource_transition_uses_certified_adapter -q`
- [ ] Run one public CLI compile smoke through the real frontend entrypoint:
  - `python -m orchestrator compile workflows/examples/effectful_let_star_normalization.orc --entry-workflow run-effectful-let-star-normalization --provider-externs-file tests/fixtures/workflow_lisp/cli/providers.json --prompt-externs-file tests/fixtures/workflow_lisp/cli/prompts.json --emit-debug-yaml .orchestrate/tmp/effectful-let-star-normalization/expanded.debug.yaml --emit-core-ast .orchestrate/tmp/effectful-let-star-normalization/core_workflow_ast.json --emit-semantic-ir .orchestrate/tmp/effectful-let-star-normalization/semantic_ir.json --emit-source-map .orchestrate/tmp/effectful-let-star-normalization/source_map.json`
- [ ] If the CLI smoke fails, fix only the sequential binding-normalization issue that caused the failure; do not broaden into unrelated runtime or syntax work.
- [ ] Record in the implementation summary which new tests were added, which exact selectors passed, and whether the final binding helper was shared by ordinary `let*`, loop-body `let*`, and private-workflow exportability exactly as planned.
- [ ] Record explicitly which existing command-boundary selectors passed, so the implementation evidence shows `command-result` and certified-adapter behavior remained unchanged rather than merely assumed.

Expected outcome:

- sequential `let*` bindings lower through one shared Stage 3 binding contract
- binding-position `match` works when the subject is already step-backed
- later bindings consume earlier lowered outputs through one local-value projection model
- loop-body `let*` and private/generated workflow exportability no longer maintain divergent acceptance rules
- non-exportable composed bindings still fail deterministically under the existing diagnostic family
- command-result and certified-adapter lowering remain explicit, deterministic command boundaries with no new hidden wrapper behavior
- the new example compiles under both `compile_stage3_module(..., validate_shared=True)` and `python -m orchestrator compile ...`

## Explicit Non-Goals

- Do not redesign `let*` syntax or typechecking.
- Do not add runtime closures, dynamic dispatch, or first-class runtime procedure values.
- Do not change write-root policy, provider/command runtime semantics, shared validation ownership, or pointer authority.
- Do not add helper scripts, inline shell/Python glue, adapter shims, or runtime-native promotion to make sequential lowering work.
- Do not reopen already implemented `ProcRef` / `bind-proc`, generic effectful match-arm lowering, composed `with-phase`, or same-file record-call behavior except for narrow compatibility fixes required by this slice.

## Implementation Notes

- Default to changing only `orchestrator/workflow_lisp/lowering.py` plus the listed tests and example workflow.
- Prefer one private helper and one small internal result carrier over scattering more special cases across `_lower_let_star(...)`, `_lower_loop_body_expr(...)`, and private-workflow exportability.
- Keep the checked-in example minimal enough that the CLI smoke can use only the existing provider and prompt extern manifests.
- If a local plan reviewer subagent is unavailable, perform a local plan-quality pass before implementation and verify that the final code change log names:
  - the shared binding helper,
  - the exact new tests,
  - the example workflow path,
  - the CLI smoke command,
  - and any residual unsupported binding shapes that still reject by design.
