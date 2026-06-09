# Effectful Match Arm Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the record-only Stage 3 restriction on generic non-loop `match` arms so effectful branch expressions that already lower through the existing branch-terminal path compile cleanly, while private/reusable workflow export checks and diagnostics stay aligned with real lowering.

**Architecture:** Keep the change inside `orchestrator/workflow_lisp/lowering.py`. Reuse the existing typed `MatchExpr` proof/join model, the shared `_lower_conditional_branch_expr(...)` and `_conditional_case_outputs(...)` helpers already used by authored `if`, and the current `_TerminalResult` / source-map machinery. Normalize each `match` arm by seeding branch-local refs for the matched variant binding, lowering the arm body through the same step-backed branch path as `if`, and projecting joined outputs from the branch terminal instead of extracting fields only from a `RecordExpr`.

**Tech Stack:** Python 3, Workflow Lisp frontend lowering pipeline, shared workflow validation via `compile_stage3_module(...)`, `pytest`, and one public `python -m orchestrator compile ...` smoke check

---

## Scope

- Current implementation scope: the approved `effectful-match-arm-normalization` design gap only.
- Primary authorities:
  - `docs/design/workflow_lisp_unified_frontend_design.md`
  - `docs/design/workflow_lisp_frontend_specification.md`
  - `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/work_instructions.md`
  - `state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/3/design-gap-architect/work_item_context.md`
  - `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/effectful-match-arm-normalization/implementation_architecture.md`
- Baseline constraint: current repository behavior, tests, shared validation, and implemented `ProcRef` / `bind-proc` semantics remain fixed unless this slice explicitly requires otherwise.
- This plan implements only the bounded generic `match` arm normalization and exportability parity described in the approved architecture.
- This plan does not implement generic `match`-as-binding lowering, new `match` syntax, proof-system redesign, runtime closures, new runtime value types, new adapters/scripts, or changes to runtime match execution semantics.

## Current Checkout Facts

- `_lower_match_expr(...)` in `orchestrator/workflow_lisp/lowering.py` still rejects every arm body that is not a `RecordExpr`.
- `_lower_conditional_branch_expr(...)`, `_inline_output_refs_for_expr(...)`, and `_conditional_case_outputs(...)` already normalize effectful authored `if` branches through shared branch-terminal logic.
- `_lower_loop_body_expr(...)` already supports effectful loop-local `match` arms by projecting branch terminals back onto the loop result contract.
- `_match_outputs_are_step_backed(...)` still assumes every arm body is a `RecordExpr`, so private/generated workflow export checks are narrower than real typechecking and the target design.
- `typecheck.py` already accepts `MatchExpr` arms whose result types join and whose effects merge; the selected gap is lowering/exportability, not typechecking.

## File Map

**Primary implementation file**
- Modify: `orchestrator/workflow_lisp/lowering.py`

**Primary test files**
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_examples.py`

**Regression-only compatibility check**
- Re-run only: `tests/test_workflow_lisp_phase_stdlib.py`

**Example workflow**
- Create: `workflows/examples/effectful_match_arm_normalization.orc`

## Required Behaviors To Prove

- A generic non-loop `match` arm lowers when the arm body is an effectful expression already supported by `_lower_conditional_branch_expr(...)`, such as `provider-result` or an effectful `let*` whose terminal outputs are step-backed.
- Each arm receives a structured local value for `arm.binding_name` derived from the matched subject terminal outputs, so nested arm expressions can keep reading variant-specific fields through the ordinary inline/local-value helpers.
- Joined outputs are projected from branch terminals through `_conditional_case_outputs(...)`; record-only field extraction is no longer the authority for generic match output projection.
- Private/generated workflow exportability checks accept the same effectful arm bodies that real lowering accepts.
- Non-exportable effectful arm bodies still fail deterministically under the existing `workflow_return_not_exportable` family, and diagnostics stay source-mapped to the authored arm body or binding site.
- Existing record-returning match arms, loop-local match normalization, and other effectful-composition slices remain compatible.
- At least one checked-in `.orc` example compiles with shared validation and also compiles through the public CLI entrypoint.

## Implementation Architecture

This slice should follow the approved implementation architecture, but the live ownership is narrower than the broader design docs: the real seam is concentrated in `orchestrator/workflow_lisp/lowering.py`.

### Unit 1: Shared Generic Match-Arm Branch Normalization

- Owns the lowering-time replacement for record-only arm handling in `_lower_match_expr(...)`.
- File:
  - Modify: `orchestrator/workflow_lisp/lowering.py`
- Stable contract:
  - thread the resolved match result type into `_lower_match_expr(...)` instead of inferring outputs from record-only assumptions
  - derive branch output contracts with `_output_contracts_for_type(...)`
  - build branch-local values for `arm.binding_name` from `binding_terminal.output_refs`
  - lower each arm body through `_lower_conditional_branch_expr(...)`
  - project joined outputs through `_conditional_case_outputs(...)`
  - keep projection-anchor behavior only for branches that lower as direct ref projections and therefore emit no child steps
  - preserve deterministic match step ids, case ids, hidden inputs, and source-map origin recording
  - keep the runtime `match` step shape and discriminant ref unchanged

Suggested helper shape:

```python
def _lower_match_arm_branch(
    arm: MatchArm,
    *,
    match_step_name: str,
    result_type: TypeRef,
    output_contracts: Mapping[str, Mapping[str, Any]],
    binding_terminal: _TerminalResult,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    arm_locals = {
        **local_values,
        arm.binding_name: _build_output_step_local_value(binding_terminal.output_refs),
    }
    case_steps, case_terminal = _lower_conditional_branch_expr(
        arm.body,
        result_type=result_type,
        step_name=f"{match_step_name}__{arm.variant_name.lower()}",
        context=context,
        local_values=arm_locals,
    )
    case_outputs = _conditional_case_outputs(
        case_terminal,
        output_contracts=output_contracts,
        span=arm.body.span,
        form_path=arm.body.form_path,
    )
    ...
```

- Keep `_lower_match_output_field(...)` only if some existing caller still needs it after the refactor. If generic match lowering is its only remaining use, delete or inline it rather than preserving a dead record-only path.

### Unit 2: Match-Arm Exportability Parity For Private/Reusable Workflows

- Owns agreement between private/generated workflow export analysis and the new generic match-arm lowering contract.
- File:
  - Modify: `orchestrator/workflow_lisp/lowering.py`
- Stable contract:
  - `_match_outputs_are_step_backed(...)` must stop hard-coding `RecordExpr` arms
  - each arm should reuse the same branch-local binding projection used by real lowering
  - each arm body should be checked through `_private_workflow_body_exports_step_backed_outputs(...)` so provider-result, command-result, workflow call, effectful `let*`, nested `match`, and composed `with-phase` cases stay consistent with the rest of private-workflow analysis
  - keep subject eligibility unchanged: match subjects still must resolve to a step-backed structured value via `_binding_terminal_for_inline_match(...)`
  - keep the existing diagnostic family; this slice changes acceptance and source mapping, not taxonomy

Recommended direction:

```python
return all(
    _private_workflow_body_exports_step_backed_outputs(
        arm.body,
        return_type_ref=return_type_ref,
        local_values={
            **local_values,
            arm.binding_name: _build_output_step_local_value(binding_terminal.output_refs),
        },
        ...,
    )
    for arm in match_expr.arms
)
```

- If the same branch-local binding map is needed in both Units 1 and 2, extract one tiny shared helper rather than duplicating local-value construction.

### Unit 3: Verification Surface

- Owns focused regressions plus one checked-in example workflow and one CLI smoke.
- Files:
  - Modify: `tests/test_workflow_lisp_lowering.py`
  - Modify: `tests/test_workflow_lisp_procedures.py`
  - Modify: `tests/test_workflow_lisp_examples.py`
  - Create: `workflows/examples/effectful_match_arm_normalization.orc`
  - Re-run only: `tests/test_workflow_lisp_phase_stdlib.py`
- Stable contract:
  - tests must assert behavior and lowered structure, not literal prompt text
  - new positive tests should prove effectful arm bodies add nested steps inside `match` cases and project outputs from those child terminals
  - new negative tests should prove non-exportable effectful arms still fail under `workflow_return_not_exportable` and land diagnostics on the authored arm body site
  - one private-workflow regression must prove exportability analysis agrees with real lowering
  - one checked-in example workflow must compile with `validate_shared=True` and through `python -m orchestrator compile ...` using the existing CLI provider/prompt extern catalogs

## Task Checklist

### Task 1: Lock The Missing Behavior In Focused Tests

**Files:**

- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_examples.py`
- Create: `workflows/examples/effectful_match_arm_normalization.orc`

- [ ] Add a focused lowering test where a step-backed union binding is matched and each arm body is a `provider-result` returning the workflow's final record type, proving generic match arms no longer need direct `RecordExpr` bodies.
- [ ] Add a second lowering test where each match arm body is an effectful `let*` whose terminal export is still step-backed, proving the shared branch path handles nested branch-local sequencing rather than only one direct call form.
- [ ] Add a negative lowering test where an effectful arm ultimately exports at least one non-step-backed leaf such as a literal status field, and assert `workflow_return_not_exportable`.
- [ ] Add a diagnostic-span regression for the negative case so the failure points at the authored effectful arm body or exported leaf site instead of only a generated match step.
- [ ] Add a private-workflow regression showing a `:lowering private-workflow` procedure with effectful match arms compiles and the generated private workflow is emitted, proving `_match_outputs_are_step_backed(...)` matches real lowering.
- [ ] Add a checked-in example workflow under `workflows/examples/` that uses `providers.execute` before and inside a `match`, and add a matching `tests/test_workflow_lisp_examples.py` compile test that runs `compile_stage3_module(..., validate_shared=True)` against it.
- [ ] Keep the checked-in example narrow enough that the CLI smoke needs only:
  - `tests/fixtures/workflow_lisp/cli/providers.json`
  - `tests/fixtures/workflow_lisp/cli/prompts.json`

Suggested test names:

- `test_compile_stage3_module_lowers_effectful_match_arm_provider_branches`
- `test_compile_stage3_module_lowers_effectful_match_arm_let_star_branches`
- `test_compile_stage3_module_rejects_non_exportable_effectful_match_arm`
- `test_compile_stage3_module_remaps_effectful_match_arm_diagnostic_to_authored_site`
- `test_private_workflow_effectful_match_arms_export_step_backed_outputs`
- `test_effectful_match_arm_normalization_orc_compiles_with_shared_validation`

Suggested positive fixture shape:

```lisp
(defworkflow provider-attempt
  ((report_path WorkReport))
  -> AttemptReport
  (let* ((attempt
           (provider-result providers.execute
             :prompt prompts.implementation.execute
             :inputs (report_path)
             :returns ImplementationState)))
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
         :returns AttemptReport)))))
```

Suggested effectful-`let*` arm shape:

```lisp
(match attempt
  ((COMPLETED completed)
   (let* ((summary
            (provider-result providers.execute
              :prompt prompts.implementation.execute
              :inputs (completed.execution_report)
              :returns AttemptReport)))
     summary))
  ((BLOCKED blocked)
   (let* ((summary
            (provider-result providers.execute
              :prompt prompts.implementation.execute
              :inputs (blocked.progress_report)
              :returns AttemptReport)))
     summary)))
```

Suggested negative fixture shape:

```lisp
(match attempt
  ((COMPLETED completed)
   (let* ((summary
            (provider-result providers.execute
              :prompt prompts.implementation.execute
              :inputs (completed.execution_report)
              :returns AttemptReport)))
     (record AttemptSummary
       :status "completed"
       :report summary.report)))
  ...)
```

**Blocking verification after Task 1:**

- [ ] If any tests are added or renamed, run:
  - `pytest --collect-only tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_examples.py -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_lowers_effectful_match_arm_provider_branches -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_lowers_effectful_match_arm_let_star_branches -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_rejects_non_exportable_effectful_match_arm -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_remaps_effectful_match_arm_diagnostic_to_authored_site -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_procedures.py::test_private_workflow_effectful_match_arms_export_step_backed_outputs -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_examples.py::test_effectful_match_arm_normalization_orc_compiles_with_shared_validation -q`

Expected before implementation: the new positive tests fail because `_lower_match_expr(...)` still raises on non-`RecordExpr` arms and `_match_outputs_are_step_backed(...)` still rejects the same arm bodies during private-workflow analysis.

### Task 2: Replace Record-Only Generic Match Lowering With Shared Branch Normalization

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`
- Inspect only unless a narrow diagnostic alignment is unavoidable: `orchestrator/workflow_lisp/typecheck.py`

- [ ] Update `_lower_let_star(...)` to pass the resolved `typed_expr.type_ref` into `_lower_match_expr(...)` so match lowering no longer depends on record-only workflow-return assumptions.
- [ ] Refactor `_lower_match_expr(...)` so it derives `output_contracts` with `_output_contracts_for_type(...)` and lowers each arm body through `_lower_conditional_branch_expr(...)` instead of `_lower_match_output_field(...)`.
- [ ] Seed each arm with `arm.binding_name` mapped to `_build_output_step_local_value(binding_terminal.output_refs)` or an equivalent tiny shared helper, so nested branch expressions can resolve variant-specific field refs through the existing inline/local-value path.
- [ ] Use `_conditional_case_outputs(...)` to construct each case's declared outputs from the returned branch terminal.
- [ ] Preserve the existing projection-anchor fallback for direct-ref branches that emit no child steps.
- [ ] Preserve match-step discriminant wiring, deterministic case ids, hidden-input behavior, and `_record_step_origin(...)` usage.
- [ ] Keep generic match subject requirements unchanged: if the subject cannot resolve to a step-backed structured terminal, continue to fail deterministically under the existing exportability diagnostic family.
- [ ] Remove or sharply narrow any helper that exists only to support record-only field extraction once the shared branch path is in place.

Implementation guardrails:

- Do not add a new AST node.
- Do not add a second runtime branch representation.
- Do not change shared validation, runtime `match` execution, provider semantics, or pointer authority.
- Do not broaden this slice into full match-as-intermediate lowering beyond the current authored positions already handled by `_lower_match_expr(...)`.

**Blocking verification after Task 2:**

- [ ] Re-run the new focused lowering tests:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_lowers_effectful_match_arm_provider_branches -q`
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_lowers_effectful_match_arm_let_star_branches -q`
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_rejects_non_exportable_effectful_match_arm -q`
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_remaps_effectful_match_arm_diagnostic_to_authored_site -q`
- [ ] Re-run one existing generic-match regression to prove record-returning arms still work:
  - `pytest tests/test_workflow_lisp_lowering.py::test_lower_workflow_definitions_supports_generic_match_outputs -q`
- [ ] Re-run one existing effectful-composition regression to prove the shared branch helpers still behave for adjacent slices:
  - `pytest tests/test_workflow_lisp_examples.py::test_with_phase_composed_binding_orc_compiles_to_typed_phase_stack -q`

Expected after Task 2: generic non-loop match arms lower successfully when the arm body already lowers through the shared branch-terminal path, record-returning arms remain valid, and non-exportable arms still fail under `workflow_return_not_exportable`.

### Task 3: Align Private/Reusable Workflow Exportability With Real Match Lowering

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`

- [ ] Update `_match_outputs_are_step_backed(...)` so each arm body is checked through `_private_workflow_body_exports_step_backed_outputs(...)` with the same branch-local binding projection used by real lowering.
- [ ] If needed, extract one tiny shared helper for branch-local match binding locals so lowering and exportability do not drift again.
- [ ] Preserve the existing handling for step-backed subjects, recursive procedure guards, generated write-root inputs, and reusable/private workflow boundary rules.
- [ ] Keep unsupported arms failing under the same exportability diagnostic family; do not add a new code path or a looser fallback that guesses runtime behavior.

**Blocking verification after Task 3:**

- [ ] Re-run:
  - `pytest tests/test_workflow_lisp_procedures.py::test_private_workflow_effectful_match_arms_export_step_backed_outputs -q`
- [ ] Re-run one existing private-workflow regression to prove ordinary step-backed export checks still behave:
  - `pytest tests/test_workflow_lisp_procedures.py::test_private_workflow_with_phase_binding_exports_step_backed_outputs -q`
- [ ] Re-run one existing loop-local match regression to show this slice did not disturb the already-supported loop path:
  - `pytest tests/test_workflow_lisp_phase_stdlib.py::test_lowering_review_loop_carries_last_review_report_through_loop_outputs -q`

Expected after Task 3: private/generated workflows accept the same effectful match arms that direct lowering accepts, and existing reusable-boundary checks still reject genuinely non-step-backed outputs.

### Task 4: Run The Focused Regression And Public Compile Proof

**Files:**

- No additional maintained source files; this task validates the changed lowering contract and the checked-in example workflow.

- [ ] Run the focused regression subset:
  - `pytest tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_examples.py tests/test_workflow_lisp_phase_stdlib.py -k "effectful_match_arm or generic_match_outputs or private_workflow_with_phase_binding or review_loop_carries_last_review_report or with_phase_composed_binding" -q`
- [ ] Re-run the shared-validation example compile explicitly:
  - `pytest tests/test_workflow_lisp_examples.py::test_effectful_match_arm_normalization_orc_compiles_with_shared_validation -q`
- [ ] Run one public CLI compile smoke against the new example so the frontend change is proven through the real entrypoint:
  - `python -m orchestrator compile workflows/examples/effectful_match_arm_normalization.orc --entry-workflow run-effectful-match-arm-normalization --provider-externs-file tests/fixtures/workflow_lisp/cli/providers.json --prompt-externs-file tests/fixtures/workflow_lisp/cli/prompts.json --emit-debug-yaml .orchestrate/tmp/effectful-match-arm-normalization/expanded.debug.yaml --emit-core-ast .orchestrate/tmp/effectful-match-arm-normalization/core_workflow_ast.json --emit-semantic-ir .orchestrate/tmp/effectful-match-arm-normalization/semantic_ir.json --emit-source-map .orchestrate/tmp/effectful-match-arm-normalization/source_map.json`
- [ ] If final test names differ from the suggested names above, keep selectors narrow and update the implementation summary rather than dropping verification.

Expected outcome:

- generic non-loop `match` arms lower through effectful branch expressions instead of only direct `RecordExpr` bodies
- private/generated workflow exportability checks agree with real lowering for the same match bodies
- variant-bound arm locals remain usable inside nested provider/command/workflow expressions
- record-only generic match coverage, loop-local match coverage, and adjacent effectful-composition slices remain compatible
- the new checked-in example compiles under both `compile_stage3_module(..., validate_shared=True)` and `python -m orchestrator compile ...`, where the CLI path already validates through the shared frontend bundle without an extra `--validate-shared` flag

## Explicit Non-Goals

- Do not redesign `MatchExpr` syntax, typing, exhaustiveness, or proof rules.
- Do not implement generic `match` as an arbitrary effectful binding expression outside the currently supported lowering positions.
- Do not add runtime closures, first-class procedure values, new adapters, helper scripts, or inline shell/Python glue.
- Do not change runtime match execution, provider/command semantics, shared validation authority, or pointer authority.
- Do not reopen already implemented `ProcRef` / `bind-proc` behavior or unrelated Workflow Lisp refactors.

## Implementation Notes

- Default to changing only `orchestrator/workflow_lisp/lowering.py` plus the listed tests and example workflow.
- Prefer one shared branch-local binding helper if both lowering and exportability need it.
- Keep `typecheck.py` unchanged unless a narrow diagnostic-plumbing mismatch is demonstrated by failing tests.
- Keep the checked-in example minimal and provider-only so the public CLI smoke can rely on the existing `providers.json` and `prompts.json` fixture catalogs.
- Record in the implementation summary which helper names changed, which tests were added, and the exact `python -m orchestrator compile ...` command and artifact paths used for verification.
