# Same-File Call Bindings For Locally Constructed Records Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the bounded Stage 3 lowering support that lets same-file workflow calls and private-workflow procedure calls accept record-typed arguments supplied as authored `record` values or local record aliases, while preserving the existing flattened ref-based runtime call boundary.

**Architecture:** Keep the change inside `orchestrator/workflow_lisp/lowering.py`. Add one shared record-aware call-binding helper that resolves a call argument through the existing inline/local-value helpers, walks the declared record boundary with `_flatten_boundary_leaf_paths(...)`, and emits ordinary flattened `call.with` leaf refs through the same final authority checks already used for scalar call bindings. Reuse that helper from `_lower_call_expr(...)` and from the private-workflow branch of `_lower_procedure_call_expr(...)`; keep typechecking, inline procedure lowering, shared validation, and runtime schemas unchanged.

**Tech Stack:** Python 3, Workflow Lisp frontend lowering pipeline, `pytest`, shared workflow validation via `compile_stage3_module(...)`, optional CLI compile smoke via `python -m orchestrator compile`

---

## Scope

- Current implementation scope: the approved `same-file-call-bindings-for-locally-constructed-records` design gap only.
- Primary authorities:
  - `docs/design/workflow_lisp_unified_frontend_design.md`
  - `docs/design/workflow_lisp_frontend_specification.md`
  - `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/work_instructions.md`
  - `state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/2/design-gap-architect/work_item_context.md`
  - `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/same-file-call-bindings-for-locally-constructed-records/implementation_architecture.md`
- Baseline constraint: current repository behavior, tests, shared validation, and accepted implemented `ProcRef` / `bind-proc` semantics remain fixed unless this slice explicitly requires otherwise.
- This plan implements only the bounded lowering normalization for record-typed same-file call arguments that are already accepted by typechecking.
- This plan does not implement new call syntax, runtime transport of structured record values, effectful-composition redesign, runtime closures, workflow loading changes, new scripts/adapters, or runtime call-step schema changes.

## Current Checkout Facts

- `_lower_call_expr(...)` already flattens record parameters with `_flatten_boundary_leaf_paths(...)`, but each leaf still flows through `_render_call_binding_ref(...)`.
- The private-workflow branch of `_lower_procedure_call_expr(...)` uses the same flatten-and-render pattern.
- `_render_call_binding_ref(...)` only succeeds when the selected leaf already resolves to a plain string ref after `_resolve_expr_local_value(...)` plus optional field-path traversal.
- `_resolve_inline_expr_value(...)`, `_resolve_inline_field_value(...)`, `_resolve_nested_local_value(...)`, `_record_expr_value_at_path(...)`, and `_build_output_step_local_value(...)` already understand local record-shaped values and authored `RecordExpr` trees.
- `typecheck.py` already accepts these record-typed call bindings. The selected gap is lowering-only, so avoid touching typechecking unless test evidence shows a narrow diagnostic mismatch.

## File Map

**Primary implementation file**
- Modify: `orchestrator/workflow_lisp/lowering.py`

**Primary test files**
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_examples.py`

**Example workflow**
- Create: `workflows/examples/same_file_record_call_binding.orc`

## Required Behaviors To Prove

- A same-file workflow call lowers when a record-typed parameter is supplied as a direct authored `RecordExpr`.
- The same workflow call lowers when the record value is first bound in `let*` and then passed by local name.
- A private-workflow procedure call lowers when its record-typed argument is supplied as a local record alias and crosses the generated runtime call boundary.
- Generated runtime call steps still emit flattened `call.with` bindings whose values are `{"ref": ...}` entries; no structured runtime call payload is introduced.
- Unsupported record leaves still fail under `workflow_signature_mismatch`, and the message names the failing record field path when practical.
- Inline procedure lowering remains unchanged.
- At least one shared-validation compile and one CLI compile smoke prove the change through the real frontend entrypoints, not only through direct unit-level helper use.

## Implementation Architecture

This slice should follow the accepted implementation architecture, but keep the live ownership narrow: the missing seam is concentrated in `orchestrator/workflow_lisp/lowering.py`.

### Unit 1: Shared Record-Aware Call-Binding Helper

- Owns the lowering-time normalization from one record-typed call argument to flattened `call.with` leaf refs.
- File:
  - Modify: `orchestrator/workflow_lisp/lowering.py`
- Stable contract:
  - accept one record-typed parameter name, declared `RecordTypeRef`, and authored argument expression
  - resolve the top-level argument through `_resolve_inline_expr_value(...)`
  - walk declared boundary leaves with `_flatten_boundary_leaf_paths(...)`
  - recover each nested leaf from either a resolved local mapping or an authored `RecordExpr`
  - pass each leaf through the same final ref-authority check already used for call bindings
  - emit ordinary flattened `call.with` entries such as `input__report: {"ref": "inputs.report_path"}`
  - reject anything that would widen the runtime call boundary beyond existing ref-based authority

Suggested helper shape:

```python
def _render_record_call_bindings(
    param_name: str,
    param_type: RecordTypeRef,
    value_expr: Any,
    *,
    local_values: Mapping[str, Any],
) -> dict[str, Any]:
    ...
```

- Keep `_build_call_bindings_from_record_value(...)` unchanged unless a tiny internal extraction makes both helpers reuse the same leaf-authority logic without broadening its current backlog-drain callers.
- If needed, add one tiny internal leaf renderer that accepts an already-resolved leaf value so the new helper and `_render_call_binding_ref(...)` share the same final `{"ref": ...}` authority rule.

### Unit 2: Workflow Calls And Private-Workflow Procedure Calls Share The Helper

- Owns parity between the two runtime-boundary call paths.
- File:
  - Modify: `orchestrator/workflow_lisp/lowering.py`
- Stable contract:
  - `_lower_call_expr(...)` uses the shared record helper for record-typed workflow parameters
  - the private-workflow branch of `_lower_procedure_call_expr(...)` uses the same helper for record-typed procedure parameters
  - scalar/path/non-record parameters continue to use `_render_call_binding_ref(...)`
  - managed write-root inputs, step naming, origin-note handling, and output projection remain unchanged
  - inline procedure lowering remains unchanged because it does not cross the runtime call boundary

### Unit 3: Diagnostics Stay Narrow And Source-Mapped

- Owns rejection behavior for unsupported record leaves.
- File:
  - Modify: `orchestrator/workflow_lisp/lowering.py`
- Stable contract:
  - keep `workflow_signature_mismatch` as the rejection family for bad call-binding leaves
  - improve message precision to include the failing parameter or field path when possible, for example ``record call binding `input.report` must lower from workflow inputs or prior outputs``
  - keep spans and form paths anchored to the authored binding expression or record field site
  - do not create a new diagnostic taxonomy

### Unit 4: Verification Surface

- Owns focused regressions plus one integration-style example workflow.
- Files:
  - Modify: `tests/test_workflow_lisp_lowering.py`
  - Modify: `tests/test_workflow_lisp_procedures.py`
  - Modify: `tests/test_workflow_lisp_examples.py`
  - Create: `workflows/examples/same_file_record_call_binding.orc`
- Stable contract:
  - tests assert behavior and lowered structure, not incidental prompt text
  - at least one example compiles with `validate_shared=True`
  - the CLI smoke uses the public compile path and existing fixture extern manifests

## Task Checklist

### Task 1: Lock The Missing Behavior In Focused Tests

**Files:**

- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_examples.py`
- Create: `workflows/examples/same_file_record_call_binding.orc`

- [ ] Add a focused lowering test for a same-file workflow call that passes a direct authored `RecordExpr` into a record-typed parameter and assert the lowered call step contains flattened ref leaves.
- [ ] Add a second lowering test for the same call shape where the record value is first bound in `let*` and then passed by local name.
- [ ] Add a negative lowering test where one record leaf is a literal or otherwise not reducible to an existing ref, and assert `workflow_signature_mismatch`.
- [ ] Add a private-workflow procedure regression that proves a record-typed procedure argument supplied as a local record alias lowers into the generated private workflow call step with flattened ref leaves.
- [ ] Add a minimal checked-in example workflow under `workflows/examples/` that exercises the local-record-alias same-file workflow-call path with only the command boundary extern, and add a matching `tests/test_workflow_lisp_examples.py` compile test that runs `compile_stage3_module(..., validate_shared=True)`.
- [ ] Prefer inline temporary modules via `_write_module(...)` for unit-level coverage in `tests/test_workflow_lisp_lowering.py` and `tests/test_workflow_lisp_procedures.py`; keep the checked-in example only for the shared-validation and CLI proof.

Suggested test names:

- `test_compile_stage3_module_lowers_same_file_call_with_direct_record_expr`
- `test_compile_stage3_module_lowers_same_file_call_with_local_record_alias`
- `test_compile_stage3_module_rejects_same_file_call_record_leaf_without_ref`
- `test_private_workflow_call_lowers_local_record_argument_into_flattened_with_bindings`
- `test_same_file_record_call_binding_orc_compiles_with_shared_validation`

Suggested same-file workflow test shape:

```lisp
(defrecord WorkflowInput
  (report WorkReport))
(defrecord WorkflowOutput
  (report WorkReport))
(defworkflow build-checks
  ((input WorkflowInput))
  -> WorkflowOutput
  (command-result run_checks
    :argv ("python" "scripts/run_checks.py" input.report)
    :returns WorkflowOutput))
(defworkflow entry
  ((report_path WorkReport))
  -> WorkflowOutput
  (let* ((input (record WorkflowInput :report report_path))
         (result (call build-checks :input input)))
    result))
```

Suggested private-workflow procedure test shape:

```lisp
(defproc build-checks
  ((input WorkflowInput))
  -> WorkflowOutput
  :effects ((uses-command run_checks))
  :lowering private-workflow
  (command-result run_checks
    :argv ("python" "scripts/run_checks.py" input.report)
    :returns WorkflowOutput))
(defworkflow entry
  ((report_path WorkReport))
  -> WorkflowOutput
  (let* ((input (record WorkflowInput :report report_path)))
    (build-checks input)))
```

**Blocking verification after Task 1:**

- [ ] If any tests are added or renamed, run:
  - `pytest --collect-only tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_examples.py -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_lowers_same_file_call_with_direct_record_expr -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_lowers_same_file_call_with_local_record_alias -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_rejects_same_file_call_record_leaf_without_ref -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_procedures.py::test_private_workflow_call_lowers_local_record_argument_into_flattened_with_bindings -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_examples.py::test_same_file_record_call_binding_orc_compiles_with_shared_validation -q`

Expected before implementation: the new positive tests fail with the current Stage 3 lowering rejection because record leaves still flow through `_render_call_binding_ref(...)`, which only accepts pre-resolved plain string refs from the top-level expression path.

### Task 2: Implement The Shared Record-Aware Call-Binding Lowering

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`

- [ ] Add one shared helper near the existing call-binding utilities that resolves a record-typed call argument and returns flattened `call.with` bindings for that parameter.
- [ ] Make the helper reuse the current authority surfaces:
  - `_resolve_inline_expr_value(...)`
  - `_resolve_inline_field_value(...)` or `_resolve_nested_local_value(...)`
  - `_record_expr_value_at_path(...)` when the source remains an authored `RecordExpr`
  - `_flatten_boundary_leaf_paths(...)`
  - the existing final ref-authority rule used by `_render_call_binding_ref(...)`
- [ ] Update `_lower_call_expr(...)` to use the helper for `RecordTypeRef` parameters instead of pushing each leaf directly through `_render_call_binding_ref(...)`.
- [ ] Update only the private-workflow branch of `_lower_procedure_call_expr(...)` to use the same helper for `RecordTypeRef` parameters.
- [ ] Keep scalar/path/non-record call arguments on the existing `_render_call_binding_ref(...)` path.
- [ ] Keep inline procedure lowering unchanged.
- [ ] Keep `call.with` values flattened and ref-based; do not admit literals, opaque mappings, pointer files, report-derived values, or generated temporary JSON as boundary authority.
- [ ] Keep managed write-root injection and terminal output projection exactly as today.
- [ ] Improve the rejection message for bad record leaves so the field path is visible without changing the diagnostic code family.

Implementation guardrails:

- Do not broaden typechecking or workflow schemas.
- Do not change shared validation ownership.
- Do not add a second lowering path, runtime value type, helper script, or adapter.
- Do not alter `_build_output_step_local_value(...)`, write-root policy, or pointer authority as part of this slice.

**Blocking verification after Task 2:**

- [ ] Re-run the new focused tests:
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_lowers_same_file_call_with_direct_record_expr -q`
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_lowers_same_file_call_with_local_record_alias -q`
  - `pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_rejects_same_file_call_record_leaf_without_ref -q`
  - `pytest tests/test_workflow_lisp_procedures.py::test_private_workflow_call_lowers_local_record_argument_into_flattened_with_bindings -q`
- [ ] Re-run one existing same-file call regression to prove ordinary call lowering still works:
  - `pytest tests/test_workflow_lisp_lowering.py::test_lower_workflow_definitions_supports_union_returning_same_file_calls -q`
- [ ] Re-run one existing private-workflow lowering regression to prove the narrowed branch still behaves:
  - `pytest tests/test_workflow_lisp_procedures.py::test_lowering_generates_private_workflow_for_reused_boundary_lowerable_procedure -q`
- [ ] Re-run one existing inline-procedure regression to prove the untouched path stays untouched:
  - `pytest tests/test_workflow_lisp_procedures.py::test_inline_procedure_lowering_accepts_literal_command_arguments -q`

Expected after Task 2: the new same-file workflow and private-workflow positive tests pass, the negative test still fails under `workflow_signature_mismatch`, existing same-file call lowering remains intact, and inline procedures remain unaffected.

### Task 3: Run The Focused Regression And End-To-End Compile Proof

**Files:**

- No additional maintained source files; this task validates the changed lowering contract and the checked-in example workflow.

- [ ] Run the focused regression subset:
  - `pytest tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_examples.py -k "same_file_call or private_workflow_call_lowers_local_record_argument or union_returning_same_file_calls or inline_procedure_lowering_accepts_literal_command_arguments" -q`
- [ ] Re-run the shared-validation example compile explicitly:
  - `pytest tests/test_workflow_lisp_examples.py::test_same_file_record_call_binding_orc_compiles_with_shared_validation -q`
- [ ] Run one public CLI compile smoke against the new example so the frontend change is proven through the real entrypoint:
  - `python -m orchestrator compile workflows/examples/same_file_record_call_binding.orc --entry-workflow run-same-file-record-call-binding --command-boundaries-file tests/fixtures/workflow_lisp/cli/commands.json --validate-shared --emit-debug-yaml .orchestrate/tmp/same-file-record-call-binding/expanded.debug.yaml --emit-core-ast .orchestrate/tmp/same-file-record-call-binding/core_workflow_ast.json --emit-semantic-ir .orchestrate/tmp/same-file-record-call-binding/semantic_ir.json --emit-source-map .orchestrate/tmp/same-file-record-call-binding/source_map.json`
- [ ] Re-run one existing example compile so additive compatibility with the current example suite is visible:
  - `pytest tests/test_workflow_lisp_examples.py::test_with_phase_composed_binding_orc_compiles_to_typed_phase_stack -q`
- [ ] If final test names differ from the suggested names above, keep the selectors narrow and update the implementation summary rather than dropping the verification.

Expected outcome:

- same-file workflow calls accept direct authored record values and local record aliases
- private-workflow procedure calls accept local record aliases across the generated runtime call boundary
- lowered runtime call steps still contain flattened `{"ref": ...}` leaf bindings only
- unsupported record leaves still fail deterministically under `workflow_signature_mismatch`
- shared validation accepts the new example workflow
- the same example also compiles through `python -m orchestrator compile ...`
- no runtime schema, write-root policy, or adapter boundary changed

## Explicit Non-Goals

- Do not add new call syntax or new type-system surfaces.
- Do not transport structured record values as first-class runtime call payloads.
- Do not redesign effectful composition, inline procedure lowering, or private-workflow loading.
- Do not add helper scripts, command adapters, inline shell/Python glue, or runtime-native effects.
- Do not reopen already implemented `ProcRef` / `bind-proc` behavior or unrelated Workflow Lisp refactors.

## Implementation Notes

- Default to changing only `orchestrator/workflow_lisp/lowering.py` plus the listed tests and example workflow.
- Prefer one new helper for record-aware call binding lowering rather than scattering field-path special cases across both call paths.
- Keep the checked-in example minimal and command-only so the CLI smoke needs only `tests/fixtures/workflow_lisp/cli/commands.json`.
- Record in the implementation summary which exact tests were added, which commands passed, and whether the final helper reused `_render_call_binding_ref(...)` directly or through a tiny shared leaf-authority extraction.
