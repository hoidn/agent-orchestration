# Workflow Lisp Phase-Family Boundary Rehabilitation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the real design-delta plan and work-item phase-family Workflow Lisp candidates clear Tranche 3A public/private boundary failures without relaxing the baseline frontend contract.

**Architecture:** Use the existing Workflow Lisp boundary projection, private executable context, provenance, and WCC schema-2 lowering route. Classify selected phase-family flattened inputs as public authored inputs, runtime-owned `PhaseCtx` inputs, compatibility bridge inputs, or generated internal inputs, then make lints and build artifacts consume that classification. Keep implementation-phase parent-callable evidence as a regression guard; do not introduce command glue, parent-drain composition, resource-transition semantics, or promotion parity claims in this slice.

**Tech Stack:** Python, pytest, Workflow Lisp compiler/lowering modules under `orchestrator/workflow_lisp/`, shared workflow bundle/provenance helpers under `orchestrator/workflow/`, `.orc` candidates under `workflows/library/lisp_frontend_design_delta/`, runtime fixtures under `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/`.

---

## Required Context

Read these before editing:

- `docs/index.md`
- `docs/design/README.md`
- `docs/capability_status_matrix.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/post_wcc_reconciliation_index.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-phase-family-boundary-rehabilitation/implementation_architecture.md`
- `tests/README.md`

Preserve these contracts:

- Workflow Lisp remains a frontend over the shared validated workflow model.
- WCC schema 2 is the accepted route for new nested-control and phase-family work; do not add helper-hoisting or a second lowering lane.
- `low_level_state_path_in_high_level_module` remains valid for public authored high-level `.orc` boundaries.
- `PhaseCtx` is private executable context, not public authored input.
- Retained legacy YAML `state/` values may survive only as explicit compatibility bridge inputs with provenance.
- Command-backed helpers stay under `docs/design/workflow_command_adapter_contract.md`; this slice must not add scripts, report parsing, pointer authority, or hidden semantic command glue.
- Do not claim YAML-primary replacement, parent-drain promotion, or migration parity from this work item.

## Current Checkout Anchors

Implementation should reuse or complete these existing surfaces:

- `orchestrator/workflow_lisp/contracts.py`
  - `GeneratedInternalInput`
  - `WorkflowBoundaryProjection`
  - `derive_workflow_boundary_fields`
  - `derive_workflow_signature_contracts`
- `orchestrator/workflow_lisp/phase_family_boundary.py`
  - selected phase-family route detection
  - `PhaseFamilyBoundaryClassification`
  - runtime-owned context and compatibility bridge classification helpers
- `orchestrator/workflow_lisp/lowering/core.py`
  - legacy-compatible finalization path
  - `LoweredWorkflow.private_exec_context_bindings`
  - `LoweredWorkflow.compatibility_bridge_inputs`
  - `_validate_projection_origin_coverage`
- `orchestrator/workflow_lisp/wcc/defunctionalize.py`
  - default WCC schema-2 workflow finalization path
  - the same boundary classification must be applied here, not only in legacy lowering
- `orchestrator/workflow_lisp/lowering/workflow_calls.py`
  - `_declare_runtime_context_hidden_inputs`
  - `PrivateExecContextBinding`
- `orchestrator/workflow/loaded_bundle.py`
  - public/runtime input projection helpers
- `orchestrator/workflow_lisp/build.py`
  - `workflow_boundary_projection.json` serialization
- `orchestrator/workflow_lisp/compiler.py`
  - required lint collection for low-level state paths

Primary test modules:

- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_key_migrations.py`
- WCC regression modules: `tests/test_workflow_lisp_wcc_characterization.py`, `tests/test_workflow_lisp_wcc_m1.py`, `tests/test_workflow_lisp_wcc_m2.py`, `tests/test_workflow_lisp_wcc_m3.py`, `tests/test_workflow_lisp_wcc_m4.py`, `tests/test_workflow_lisp_wcc_m5.py`

Real phase-family inputs:

- `workflows/library/lisp_frontend_design_delta/plan_phase.orc`
- `workflows/library/lisp_frontend_design_delta/implementation_phase.orc`
- `workflows/library/lisp_frontend_design_delta/work_item.orc`
- `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/plan_phase.orc`
- `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/implementation_phase.orc`
- `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/work_item.orc`

## Out Of Scope

- WCC `IfExpr` implementation unless a fresh regression proves it is still missing.
- Selector typed projection.
- Resource-transition ownership.
- Parent backlog-drain composition.
- Migration parity or YAML-primary promotion.
- Broad lint policy changes for unrelated workflows.
- New command adapters, scripts, report parsing, pointer-authority behavior, or inline Python/shell semantics.

## File Structure

Modify, if incomplete:

- `orchestrator/workflow_lisp/phase_family_boundary.py`
  - Keep selected-route detection and classification here.
  - Keep it frontend-owned and free of runtime execution behavior.
- `orchestrator/workflow_lisp/wcc/defunctionalize.py`
  - Apply classification in `_lower_one_wcc_workflow` before public/internal span maps and finalized `WorkflowBoundaryProjection` are computed.
- `orchestrator/workflow_lisp/lowering/core.py`
  - Apply the same classification in legacy-compatible lowering.
  - Keep `_validate_projection_origin_coverage` valid for reclassified internal flattened inputs.
- `orchestrator/workflow_lisp/lowering/workflow_calls.py`
  - Reuse hidden context binding for helper/private workflow `PhaseCtx` transport.
- `orchestrator/workflow_lisp/compiler.py`
  - Ensure required lints inspect classified public boundaries or narrowly skip only selected private/bridge phase-family inputs.
- `orchestrator/workflow_lisp/build.py`
  - Change only if existing `LoweredWorkflow` / bundle provenance is not serialized.

Test:

- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_key_migrations.py`
- Add or update focused fixtures only when the real design-delta candidates need expected boundary labels.

Do not modify unless a failing test proves it is necessary:

- `workflows/library/scripts/**`
- `specs/**`
- unrelated `workflows/examples/**`
- parent drain workflow YAML

## Task 1: Baseline And Characterization

**Files:**

- Test: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Test: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] **Step 1: Run collect-only for the affected modules**

```bash
python -m pytest --collect-only tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_key_migrations.py -q
```

Expected: collection succeeds. If collection fails before edits, fix collection first.

- [ ] **Step 2: Capture current boundary behavior**

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "plan_phase_candidate or implementation_phase_candidate or work_item_candidate_compiles or parent_call_work_item_compiles" -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "design_delta_plan_phase_boundary or design_delta_work_item_boundary_labels or runtime_context_inputs or compatibility_bridge" -q
```

Expected before or during implementation: failures, if any, identify the active gap. Old blockers must not reappear unnoticed:

- `unsupported IfExpr`
- `union_return_variant_ambiguous`
- `union_return_variant_incompatible`
- `proc_private_workflow_boundary_invalid`

- [ ] **Step 3: Ensure direct-entry `plan_phase.orc` has a public/private boundary test**

In `tests/test_workflow_lisp_build_artifacts.py`, add or preserve a test named like `test_design_delta_plan_phase_boundary_hides_phase_context_and_bridge_inputs`. It must compile `workflows/library/lisp_frontend_design_delta/plan_phase.orc`, assert `entry_result.lowering_schema_version == 2`, and prove:

```python
runtime_context_inputs == {
    "phase-ctx__run__run-id",
    "phase-ctx__run__state-root",
    "phase-ctx__run__artifact-root",
    "phase-ctx__phase-name",
    "phase-ctx__state-root",
    "phase-ctx__artifact-root",
}
assert runtime_context_inputs.isdisjoint(public_inputs)
assert "phase-ctx__state-root" not in public_inputs
```

Also assert the direct-entry runtime context inputs appear in `LoweredWorkflow.boundary_projection.generated_internal_inputs` with reason `runtime_owned_context` and in `LoweredWorkflow.origin_map.internal_input_spans`, not `authored_input_spans`.

- [ ] **Step 4: Ensure work-item compatibility bridge artifact coverage exists**

In `tests/test_workflow_lisp_build_artifacts.py`, add or preserve a test named like `test_design_delta_work_item_boundary_labels_legacy_state_inputs_as_compatibility_bridge`. It must compile the real work-item route under default schema 2 and assert:

```python
expected_bridge_inputs = {
    "selection_bundle_path",
    "manifest_path",
    "architecture_bundle_path",
    "progress_ledger_path",
    "run_state_path",
}
assert expected_bridge_inputs.issubset(lowered.compatibility_bridge_inputs)
assert {internal_inputs[name] for name in expected_bridge_inputs} == {"compatibility_bridge"}
assert expected_bridge_inputs.issubset(lowered.origin_map.internal_input_spans)
assert expected_bridge_inputs.isdisjoint(lowered.origin_map.authored_input_spans)
```

- [ ] **Step 5: Ensure compile tests assert Tranche 3A blockers are absent**

In `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`, add or preserve helper assertions so work-item compile tests reject these diagnostics:

```python
assert "low_level_state_path_in_high_level_module" not in diagnostic_codes
assert "workflow_boundary_type_invalid" not in diagnostic_codes
assert not any("unsupported `IfExpr`" in diagnostic.message for diagnostic in diagnostics)
```

If compile succeeds, assert the entry result uses schema 2 and contains the expected work-item bundle.

## Task 2: Complete Phase-Family Boundary Classification

**Files:**

- Modify: `orchestrator/workflow_lisp/phase_family_boundary.py`
- Test: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] **Step 1: Keep selected-route detection narrow**

`is_selected_phase_family_workflow(workflow_name)` must return true only for:

- workflows whose names start with `lisp_frontend_design_delta/`
- explicitly listed parent-call work-item routes, such as `design_delta_parent_calls_work_item::run-parent-work-item`

Do not globally classify arbitrary high-level workflows.

- [ ] **Step 2: Classify top-level `PhaseCtx` as runtime-owned context**

Use structural type recognition:

```python
def is_phase_context_type(type_ref: TypeRef) -> bool:
    return isinstance(type_ref, RecordTypeRef) and short_type_name(type_ref) == "PhaseCtx"
```

Every flattened field from a `PhaseCtx` parameter in selected phase-family workflows must be classified as `runtime_owned_context`.

- [ ] **Step 3: Classify only selected legacy state inputs as compatibility bridges**

Recognize only these parameter names and type families:

```python
COMPATIBILITY_BRIDGE_PARAM_NAMES = {
    "selection_bundle_path",
    "manifest_path",
    "architecture_bundle_path",
    "progress_ledger_path",
    "run_state_path",
}
COMPATIBILITY_BRIDGE_TYPE_NAMES = {
    "SelectionBundlePath",
    "ProgressLedger",
    "RunStatePath",
    "StateFile",
    "StateFileExisting",
}
```

Also accept a matching `PathTypeRef` under `state` only when the parameter name is in the allowlist above.

- [ ] **Step 4: Preserve public authored inputs**

Do not classify these as private or bridge values:

- steering paths
- target/baseline design paths
- plan paths
- reports under `artifacts/`
- provider choices
- prompt files/assets
- arbitrary `state/` paths outside the selected phase-family route

- [ ] **Step 5: Preserve unclassified low-level state evidence**

If a selected phase-family workflow still has a `state/` input that is neither `PhaseCtx`, compatibility bridge, nor generated internal input, keep it public and expose it as an unclassified low-level input so linting can fail closed.

## Task 3: Wire Classification Into WCC And Legacy Finalization

**Files:**

- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Modify: `orchestrator/workflow_lisp/lowering/core.py`
- Modify: `orchestrator/workflow_lisp/phase_family_boundary.py`
- Test: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] **Step 1: Apply classification before span/projection finalization**

In both WCC and legacy lowering, call a shared helper after `derive_workflow_signature_contracts(...)` and `_LoweringContext` creation, but before:

- `authored_input_spans`
- `internal_input_spans`
- finalized `WorkflowBoundaryProjection.generated_internal_inputs`
- `_validate_projection_origin_coverage(...)`
- `LoweredWorkflow(...)` construction

For each runtime-owned context input:

```python
context.internal_generated_input_reasons[name] = "runtime_owned_context"
context.authored_generated_inputs.discard(name)
```

For each compatibility bridge input:

```python
context.internal_generated_input_reasons[name] = "compatibility_bridge"
context.authored_generated_inputs.discard(name)
```

Keep the name in `authored_mapping["inputs"]`; runtime/shared validation still needs the contract.

- [ ] **Step 2: Record direct-entry `PhaseCtx` private context binding**

When runtime-owned `PhaseCtx` flattened inputs are present, append one `PrivateExecContextBinding` with:

- `source_param_name="phase-ctx"`
- `context_family="PhaseCtx"`
- `bridge_class="runtime_owned_context"`
- `generated_input_names` set to the sorted runtime-owned field names
- `required_capabilities=private_exec_context_capabilities("PhaseCtx")`
- `derived_phase_identity` derived from the selected phase entry when available (`plan`, `implementation`, `work-item`), otherwise `None`
- source provenance from the workflow parameter/source origin

Do not synthesize a public default as promotion evidence.

- [ ] **Step 3: Return compatibility and binding metadata from WCC**

The WCC `LoweredWorkflow` return must set:

```python
private_exec_context_bindings=tuple(context.private_exec_context_bindings)
compatibility_bridge_inputs=tuple(
    name
    for name, reason in sorted(context.internal_generated_input_reasons.items())
    if reason == "compatibility_bridge"
)
```

Do not rely on defaults; build artifacts and bundle helpers consume this metadata.

- [ ] **Step 4: Keep origin validation fail-closed**

Update or preserve `_validate_projection_origin_coverage(...)` so a flattened input is valid when it has:

- authored origin in `authored_input_spans`, or
- internal origin in `internal_input_spans` and the same name appears in `boundary_projection.generated_internal_inputs`.

It must still fail with `workflow_boundary_projection_missing_origin` if a flattened input or generated internal input lacks source provenance.

Minimal intended check:

```python
internal_input_names = {
    item.generated_name
    for item in boundary_projection.generated_internal_inputs
}
missing = next(
    (
        field.generated_name
        for field in boundary_projection.flattened_inputs
        if field.generated_name not in authored_input_spans
        and not (
            field.generated_name in internal_input_names
            and field.generated_name in internal_input_spans
        )
    ),
    None,
)
```

- [ ] **Step 5: Run artifact selectors**

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "design_delta_plan_phase_boundary or design_delta_work_item_boundary_labels or promoted_entry_runtime_context_inputs_stay_internal or boundary_projection_serializer_uses_typed_bundle_compatibility_split" -q
```

Expected: PASS under default schema 2. Existing promoted-entry hidden context behavior remains green.

## Task 4: Make Low-Level State Lint Consume Classified Public Boundaries

**Files:**

- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/phase_family_boundary.py` only if the classifier needs a lint-facing helper
- Test: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Test: `tests/test_workflow_lisp_diagnostics.py` only if adding a small negative fixture is necessary

- [ ] **Step 1: Locate required lint collection**

Inspect `_collect_stage3_required_lint_diagnostics(...)` in `orchestrator/workflow_lisp/compiler.py`.

- [ ] **Step 2: Exempt only proven private or compatibility fields**

Ensure `low_level_state_path_in_high_level_module` is not emitted for selected phase-family fields classified as:

- `runtime_owned_context`
- `compatibility_bridge`
- `managed_write_root`

Acceptable implementation choices:

- preferred: run a projection-aware lint after lowering, where the public/private split is known;
- acceptable: keep the pre-lowering lint but narrowly skip only selected phase-family `PhaseCtx` and compatibility bridge parameters by reusing classifier predicates.

Do not globally exempt `PathTypeRef(under="state")`.

- [ ] **Step 3: Add or preserve a negative unrelated public state-path regression**

Keep a test proving an unrelated high-level `.orc` public `state/` path still emits `low_level_state_path_in_high_level_module` under strict lint.

Expected assertion:

```python
assert "low_level_state_path_in_high_level_module" in {d.code for d in exc_info.value.diagnostics}
```

- [ ] **Step 4: Run lint-focused selectors**

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_plan_phase_candidate_compiles_with_stdlib_review_loop tests/test_workflow_lisp_diagnostics.py -k "low_level_state_path or required_lint" -q
```

Expected: plan phase compiles; unrelated public low-level state path still fails in strict lint.

## Task 5: Preserve Helper/Private Workflow Phase Context Transport

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering/workflow_calls.py`
- Modify: `orchestrator/workflow_lisp/lowering/core.py` only if call-site metadata must pass through context
- Test: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`

- [ ] **Step 1: Reuse existing hidden binding mechanics**

Use `_declare_runtime_context_hidden_inputs(...)` and existing `PrivateExecContextBinding` behavior for child calls that need `PhaseCtx`. Do not introduce a new carrier model.

- [ ] **Step 2: Limit helper/private behavior to selected phase-family routes**

Allow hidden context binding for:

- selected phase-family workflows;
- generated/private child workflows in the same phase-family graph; and
- existing promoted-entry hidden context routes.

Do not make arbitrary user-authored workflow boundaries accept `PhaseCtx` as public input.

- [ ] **Step 3: Keep ambiguous context capture diagnostic**

If a helper/private workflow receives or captures phase context but the source phase identity cannot be derived from an ancestor runtime-owned context or explicit caller binding, fail with an owned diagnostic. Reuse an existing diagnostic such as `promoted_entry_hidden_phase_ctx_ambiguous` if accurate; otherwise add a narrow diagnostic such as `phase_family_helper_context_boundary_invalid`.

- [ ] **Step 4: Run compile-focused phase-family selectors**

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "work_item_candidate_compiles or parent_call_work_item_compiles or plan_phase_candidate or implementation_phase_candidate" -q
```

Expected: no Tranche 3A boundary/path errors. Implementation-phase evidence remains green.

## Task 6: Flip Or Preserve Real Work-Item Smoke Evidence

**Files:**

- Modify: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`

- [ ] **Step 1: Ensure work-item smoke tests execute runtime helpers**

The following tests should call their execution helpers directly rather than expecting a boundary compile failure:

- `test_design_delta_work_item_candidate_smokes_complete_and_blocked_recovery_routes`
- `test_design_delta_work_item_candidate_smokes_terminal_blocked_route`
- `test_design_delta_parent_call_work_item_smokes_complete_and_blocked_recovery_routes`
- `test_design_delta_parent_call_work_item_smokes_terminal_blocked_route`

Use existing helpers such as:

- `_execute_design_delta_work_item_route(...)`
- `_execute_design_delta_parent_call_work_item_route(...)`

Assert concrete runtime state, provider calls, and expected terminal artifacts. For completed routes, assert status/output state. For blocked routes, assert the blocked terminal state and expected artifact/report existence.

- [ ] **Step 2: Preserve implementation-phase regression guards**

Do not weaken:

- `test_design_delta_implementation_phase_candidate_compiles_with_variant_and_review_loop`
- `test_design_delta_implementation_phase_candidate_smokes_completed_and_blocked_routes`
- `test_design_delta_parent_call_implementation_phase_smokes_completed_and_blocked_routes`

- [ ] **Step 3: Run work-item smoke selectors**

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "work_item_candidate_smokes or parent_call_work_item_smokes" -q
```

Expected: PASS, or fail only with a documented later-tranche diagnostic that is not `low_level_state_path_in_high_level_module`, `workflow_boundary_type_invalid`, or WCC `IfExpr` route unsupported.

## Task 7: Build Artifact And Boundary Projection Evidence

**Files:**

- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `orchestrator/workflow_lisp/build.py` only if serialization omits already-recorded provenance

- [ ] **Step 1: Assert public inputs exclude private/bridge fields**

Use existing build helpers in `tests/test_workflow_lisp_build_artifacts.py` to inspect `workflow_boundary_projection.json` for `lisp_frontend_design_delta/work_item::run-work-item`.

Required assertions:

```python
assert "phase-ctx__state-root" not in workflow_projection["boundary"]["public_input_names"]
assert "run_state_path" not in workflow_projection["boundary"]["public_input_names"]
assert set(workflow_projection["boundary"]["private_compatibility_bridge_inputs"]).issuperset(
    {
        "selection_bundle_path",
        "manifest_path",
        "architecture_bundle_path",
        "progress_ledger_path",
        "run_state_path",
    }
)
assert workflow_projection["boundary"]["private_runtime_context_bindings"]
```

- [ ] **Step 2: Assert private runtime context binding metadata**

For every relevant binding:

```python
assert binding["context_family"] == "PhaseCtx"
assert binding["bridge_class"] == "runtime_owned_context"
assert binding["generated_input_names"]
```

If bundle-level provenance already records source path/line/form path, prefer asserting that existing data. Do not add a second build artifact schema.

- [ ] **Step 3: Preserve command adapter lineage visibility**

Keep or add a test proving the work-item command-backed helpers remain visible as declared command boundaries, including:

- `materialize_lisp_frontend_work_item_inputs`
- `classify_lisp_frontend_work_item_terminal`
- `select_lisp_frontend_blocked_recovery_route`

This verifies boundary classification did not hide command semantics.

- [ ] **Step 4: Run artifact selectors**

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "workflow_boundary_projection or design_delta_work_item or runtime_context_inputs or compatibility_bridge or command_boundary_lineage" -q
```

Expected: PASS, with schema-2 assertions present in the design-delta tests.

## Task 8: Regression Band And Final Checks

**Files:**

- Modify docs only if implementation changes user-visible behavior beyond this architecture. Prefer no broad doc changes; the implementation architecture already records the design gap.

- [ ] **Step 1: Run collect-only if tests were added or renamed**

```bash
python -m pytest --collect-only tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_key_migrations.py -q
```

Expected: collection succeeds.

- [ ] **Step 2: Run focused boundary selectors**

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "design_delta_plan_phase_boundary or design_delta_work_item_boundary_labels" -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "work_item_candidate_compiles or parent_call_work_item_compiles or work_item_candidate_smokes or parent_call_work_item_smokes" -q
```

Expected: PASS under default WCC schema 2.

- [ ] **Step 3: Run key migration boundary regressions**

```bash
python -m pytest tests/test_workflow_lisp_key_migrations.py -k "runtime_context or public_inputs or promoted_entry" -q
```

Expected: PASS. Existing promoted-entry hidden context behavior does not regress.

- [ ] **Step 4: Run WCC regression tests**

```bash
python -m pytest tests/test_workflow_lisp_wcc_characterization.py tests/test_workflow_lisp_wcc_m1.py tests/test_workflow_lisp_wcc_m2.py tests/test_workflow_lisp_wcc_m3.py tests/test_workflow_lisp_wcc_m4.py tests/test_workflow_lisp_wcc_m5.py -q
```

Expected: PASS. Any failure means the accepted WCC route was changed accidentally.

- [ ] **Step 5: Run full affected modules**

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -q
```

Expected: PASS, unless a remaining compile failure is explicitly assigned to a later tranche. If a later-tranche diagnostic remains, update the affected test name/assertion so Tranche 3A is not falsely marked blocked.

- [ ] **Step 6: Run whitespace check**

```bash
git diff --check
```

Expected: no output.

## Completion Criteria

The work item is complete only when:

- `plan_phase.orc` and the real work-item phase-family candidate no longer fail because `PhaseCtx`, phase state roots, generated write roots, or retained legacy `state/` paths are public high-level inputs.
- The helper/private workflow route used by work-item composition no longer fails with `workflow_boundary_type_invalid` for phase-family context transport.
- Public boundary inspection excludes `PhaseCtx` leaves, generated write roots, and compatibility `state/` values.
- Boundary projection identifies private runtime context bindings and compatibility bridge inputs.
- Design-delta boundary/projection tests assert `lowering_schema_version == 2`.
- Existing implementation-phase parent-callable WCC compile/smoke evidence still passes.
- WCC regression tests still pass.
- Any remaining failure is assigned to a later documented tranche and is not one of:
  - `low_level_state_path_in_high_level_module`
  - `workflow_boundary_type_invalid`
  - WCC `IfExpr` route unsupported
- No new command glue, report parsing, pointer authority, resource-transition semantics, parent-drain composition, or promotion parity behavior is introduced.

## Final Verification Commands

Run these before reporting completion:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_key_migrations.py -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "design_delta_plan_phase_boundary or design_delta_work_item_boundary_labels" -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -q
python -m pytest tests/test_workflow_lisp_key_migrations.py -k "runtime_context or public_inputs or promoted_entry" -q
python -m pytest tests/test_workflow_lisp_wcc_characterization.py tests/test_workflow_lisp_wcc_m1.py tests/test_workflow_lisp_wcc_m2.py tests/test_workflow_lisp_wcc_m3.py tests/test_workflow_lisp_wcc_m4.py tests/test_workflow_lisp_wcc_m5.py -q
git diff --check
```
