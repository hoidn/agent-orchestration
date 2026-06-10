# Workflow Lisp Phase-Family Boundary Rehabilitation Post-IfExpr Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the selected real design-delta plan/work-item Workflow Lisp routes clear the post-IfExpr Tranche 3A boundary failures without exposing `PhaseCtx`, generated write roots, or retained YAML `state/` paths as public authored `.orc` inputs.

**Architecture:** Reuse the existing WCC schema 2 route, `WorkflowBoundaryProjection`, `GeneratedInternalInput`, `PrivateExecContextBinding`, source maps, loaded-bundle helpers, and Semantic IR state-layout projection. Complete the selected `lisp_frontend_design_delta/*` phase-family boundary classification and hidden context/call transport, then convert current expected-failure tests into positive compile, artifact, and controlled fake-runtime smoke evidence.

**Tech Stack:** Python, pytest, Workflow Lisp `.orc`, WCC lowering, shared workflow validation, `LoadedWorkflowBundle`, Semantic IR, source-map/build artifacts.

---

## Authorities And Scope

Read these before implementation:

- `docs/index.md`
- `docs/design/README.md`
- `docs/capability_status_matrix.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/post_wcc_reconciliation_index.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`, especially Sections 14.4A, 14.5, 14.6, 14.7, 18.2, 22, 25, and 29
- `docs/design/workflow_lisp_frontend_specification.md`, especially Sections 0, 19, 20, 45, 47, 59, 74, 83, and the final design center
- `docs/design/workflow_lisp_runtime_migration_foundation.md`
- `docs/design/workflow_lisp_core_calculus_middle_end.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/lisp_workflow_drafting_guide.md`
- `specs/dsl.md`, `specs/io.md`, `specs/providers.md`, `specs/state.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-phase-family-boundary-rehabilitation-post-ifexpr/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/check_commands.json`

Bounded implementation scope:

- Own selected design-delta phase-family boundary classification for `plan_phase.orc` and `work_item.orc`.
- Hide selected direct `PhaseCtx` flattened leaves as runtime-owned context inputs.
- Label selected legacy `selection_bundle_path`, `manifest_path`, `architecture_bundle_path`, `progress_ledger_path`, and `run_state_path` inputs as compatibility bridge values where the selected route uses them.
- Carry `PhaseCtx` through generated/private helper and parent-call boundaries using accepted hidden runtime-owned context binding, not public workflow boundary fields.
- Make `low_level_state_path_in_high_level_module` consume the classified public boundary and keep rejecting unrelated public `state/` path inputs.
- Preserve command-backed helper visibility and certified adapter metadata; do not add hidden scripts, report parsing, pointer authority, resource-transition semantics, or parent-drain composition.

Current facts to preserve:

- `orchestrator/workflow_lisp/phase_family_boundary.py` already has conservative selected-route classification.
- The direct phase-family classifier is selected for the `lisp_frontend_design_delta/` module family, and the separate parent-call bridge fixture
  `design_delta_parent_calls_work_item::run-parent-work-item` remains explicitly eligible through `PHASE_FAMILY_PARENT_WORKFLOW_NAMES`.
- `orchestrator/workflow_lisp/lowering/core.py` and `orchestrator/workflow_lisp/wcc/defunctionalize.py` already call the classifier.
- Loaded-bundle public input helpers already exclude `runtime_context_inputs` and `compatibility_bridge_inputs`.
- Build-artifact projection and Semantic IR already serialize these classes for some routes.
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py` already has positive compile coverage for work-item runtime and parent-call routes, while the remaining work-item and parent-call smoke tests still expect compile failure; those smoke expected failures must become positive evidence.

## File Map

- Modify: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
  - Preserve positive compile tests for real work-item and parent-call work-item routes, and convert remaining expected-failure smoke tests into execution assertions.
  - Keep a readiness assertion that old returned-variant, unsupported `IfExpr`, and private-workflow export blockers are absent if a later-tranche diagnostic still remains.
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
  - Add artifact/public-boundary assertions for real `work_item.orc`, direct `plan_phase.orc`, parent-call work-item boundary, source-map provenance, and Semantic IR layout entries.
- Modify: `tests/test_workflow_lisp_key_migrations.py`
  - Add or tighten regression coverage that promoted/public input helpers hide phase-family context and compatibility bridge inputs.
- Modify: `tests/test_workflow_lisp_wcc_characterization.py` and `tests/test_workflow_lisp_wcc_m4.py`
  - Add route-pin regression checks only if implementation touches WCC context transport or diagnostics.
- Modify: `orchestrator/workflow_lisp/phase_family_boundary.py`
  - Complete selected-route classifier and expose helper predicates/records needed by lints or call lowering.
- Modify: `orchestrator/workflow_lisp/lowering/core.py`
  - Ensure direct-entry `PhaseCtx` classification, generated internal input reasons, origins, `PrivateExecContextBinding`, and compatibility bridge inputs are preserved in legacy/default lowering.
- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py`
  - Mirror the same projection behavior for WCC schema 2 output.
- Modify: `orchestrator/workflow_lisp/lowering/workflow_calls.py`
  - Ensure omitted `PhaseCtx` on selected parent calls can be satisfied through hidden runtime-owned context metadata, and explicit `phase-ctx` passed to helper/private workflows does not become an invalid public boundary.
- Modify: `orchestrator/workflow_lisp/lowering/phase_scope.py` or `orchestrator/workflow_lisp/phase.py`
  - Only if phase identity derivation is duplicated or missing for `run-work-item` and helper/private workflow bindings.
- Modify: `orchestrator/workflow_lisp/compiler.py`
  - Update the required lint to evaluate public authored boundary exposure rather than raw signature types for the selected classified phase-family route.
- Modify: `orchestrator/workflow_lisp/build.py` and `orchestrator/workflow_lisp/source_map.py`
  - Only if artifact/source-map serialization misses real-route runtime context or compatibility bridge provenance.
- Modify: `orchestrator/workflow/semantic_ir.py`
  - Only if existing `runtime_context_input` or `compatibility_bridge_input` state-layout entries are missing for the real route after validation.

Do not modify unrelated workflows, parent-drain mechanics, selector routing, resource-transition semantics, or broad legacy lint policy.

## Task 1: Baseline Failing Tests For The Selected Boundary Gap

**Files:**
- Modify: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] **Step 1: Keep or add the work-item positive compile test**

In `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`, ensure this test exists and is the authoritative passing compile assertion for the real work-item runtime entrypoint:

```python
def test_design_delta_work_item_candidate_compiles_with_phase_family_boundary_contracts(tmp_path: Path) -> None:
    workflow_path, result = _compile_design_delta_work_item_runtime_entrypoint(tmp_path)
    assert workflow_path.name == "work_item.orc"
    bundle = result.entry_result.validated_bundles[
        "lisp_frontend_design_delta/work_item::run-work-item"
    ]
    public_inputs = set(workflow_public_input_contracts(bundle))

    assert "phase-ctx__state-root" not in public_inputs
    assert "selection_bundle_path" not in public_inputs
    assert "manifest_path" not in public_inputs
    assert "architecture_bundle_path" not in public_inputs
    assert "progress_ledger_path" not in public_inputs
    assert "run_state_path" not in public_inputs
```

Keep the existing post-IfExpr assertion helper, but use it only inside explicit diagnostic-characterization tests, not as the passing condition for this route. If this test is already present, tighten it rather than duplicating it.

- [ ] **Step 2: Keep or add parent-call compile coverage**

Ensure a positive test covers `_compile_design_delta_parent_call_work_item_entrypoint(tmp_path)`:

```python
def test_design_delta_parent_call_work_item_compiles_with_hidden_phase_context(tmp_path: Path) -> None:
    _workflow_path, result, lowered_by_name = _compile_design_delta_parent_call_work_item_entrypoint(tmp_path)
    bundle = result.entry_result.validated_bundles[
        "design_delta_parent_calls_work_item::run-parent-work-item"
    ]
    public_inputs = set(workflow_public_input_contracts(bundle))
    assert "phase-ctx__state-root" not in public_inputs
    assert "selection_bundle_path" not in public_inputs
    assert "manifest_path" not in public_inputs
    assert "architecture_bundle_path" not in public_inputs
    assert "progress_ledger_path" not in public_inputs
    assert "run_state_path" not in public_inputs
    assert any(
        "lisp_frontend_design_delta/work_item::run-work-item" in name
        for name in lowered_by_name
    )
```

If the route still fails while implementation is incomplete, keep that failure in a separate diagnostic-characterization test and assert that it is not one of:

- `union_return_variant_ambiguous`
- `union_return_variant_incompatible`
- `proc_private_workflow_boundary_invalid`
- an unsupported `IfExpr` message
- `low_level_state_path_in_high_level_module`
- `workflow_boundary_type_invalid`

- [ ] **Step 3: Convert work-item smoke tests from expected failure to execution**

Update these tests to call the existing fake-runtime helpers instead of expecting `LispFrontendCompileError`:

- `test_design_delta_work_item_candidate_smokes_complete_and_blocked_recovery_routes`
- `test_design_delta_work_item_candidate_smokes_terminal_blocked_route`
- `test_design_delta_parent_call_work_item_smokes_complete_and_blocked_recovery_routes`
- `test_design_delta_parent_call_work_item_smokes_terminal_blocked_route`

Use existing helpers:

```python
_execute_design_delta_work_item_route(
    tmp_path / "completed",
    plan_variant="APPROVED",
    implementation_variant="COMPLETED",
    work_item_source="DRAFT_DESIGN_GAP",
)
```

```python
_execute_design_delta_work_item_route(
    tmp_path / "blocked",
    plan_variant="APPROVED",
    implementation_variant="BLOCKED",
    work_item_source="DRAFT_DESIGN_GAP",
)
```

```python
_execute_design_delta_work_item_route(
    tmp_path / "plan-blocked",
    plan_variant="BLOCKED",
    implementation_variant="COMPLETED",
    work_item_source="DRAFT_DESIGN_GAP",
)
```

Mirror the same cases through `_execute_design_delta_parent_call_work_item_route(...)`.

Expected assertions:

- final state status is `completed`;
- provider call sequence matches the route (`fake-plan-draft`, `fake-plan-review`, implementation providers only on approved plan route, and recovery classifier only on blocked implementation route);
- emitted summary/report files exist under the fake workspace;
- route-specific output variant is present in `state["workflow_outputs"]` or the equivalent workflow output state already used by nearby tests.

- [ ] **Step 4: Add or tighten build-artifact assertions for real work-item direct boundary**

In `tests/test_workflow_lisp_build_artifacts.py`, add a test near `test_design_delta_work_item_boundary_labels_legacy_state_inputs_as_compatibility_bridge`, or extend that local group if a narrower assertion already exists:

```python
def test_design_delta_work_item_boundary_hides_phase_context_and_bridge_inputs(tmp_path: Path) -> None:
    request = _design_delta_work_item_request(tmp_path)
    build = _build_module()
    built = build.build_frontend_bundle(request)
    bundle = built.compile_result.entry_result.validated_bundles[
        "lisp_frontend_design_delta/work_item::run-work-item"
    ]
    public_inputs = set(_workflow_public_input_contracts(bundle))
    runtime_context_inputs = set(_workflow_runtime_context_inputs(bundle))
    boundary = _workflow_boundary_projection(bundle)

    assert runtime_context_inputs == {
        "phase-ctx__run__run-id",
        "phase-ctx__run__state-root",
        "phase-ctx__run__artifact-root",
        "phase-ctx__phase-name",
        "phase-ctx__state-root",
        "phase-ctx__artifact-root",
    }
    assert runtime_context_inputs.isdisjoint(public_inputs)
    assert {
        "selection_bundle_path",
        "manifest_path",
        "architecture_bundle_path",
        "progress_ledger_path",
        "run_state_path",
    }.issubset(set(boundary.private_compatibility_bridge_inputs))
```

Adjust exact helper calls to match the current build helper shape. If `build_frontend_bundle` currently fails, leave this as the first red test for Task 2.

- [ ] **Step 5: Run the new focused tests and confirm they fail for the boundary reasons**

Run:

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "work_item_candidate or parent_call_work_item" -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "design_delta_work_item_boundary or runtime_context_inputs or compatibility_bridge" -q
```

Expected before implementation if the code is not yet complete: failures show compile/boundary/classification gaps, not returned-variant ambiguity, unsupported `IfExpr`, or old private-workflow export blockers. If these tests already pass, treat that as baseline evidence and continue with Tasks 2-6 to preserve helper transport, lint, source-map, Semantic IR, and smoke coverage.

## Task 2: Complete Selected Phase-Family Classification

**Files:**
- Modify: `orchestrator/workflow_lisp/phase_family_boundary.py`
- Modify: `orchestrator/workflow_lisp/lowering/core.py`
- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py`

- [ ] **Step 1: Extend the classifier record without changing unrelated callers**

Update `PhaseFamilyBoundaryClassification` to expose all classes needed by downstream code:

```python
@dataclass(frozen=True)
class PhaseFamilyBoundaryClassification:
    runtime_owned_context_inputs: tuple[str, ...] = ()
    compatibility_bridge_inputs: tuple[str, ...] = ()
    public_authored_inputs: tuple[str, ...] = ()
    unclassified_low_level_inputs: tuple[str, ...] = ()
```

Preserve backward compatibility by keeping existing attributes unchanged.

- [ ] **Step 2: Keep direct phase-family route selection narrow while preserving the parent-call bridge**

Keep direct phase-family workflow classification limited to names starting with:

```python
PHASE_FAMILY_MODULE_PREFIX = "lisp_frontend_design_delta/"
```

Do not hide `state/` paths for arbitrary workflows.

At the same time, preserve the narrow parent-call eligibility path for the selected fixture. Keep `PHASE_FAMILY_PARENT_WORKFLOW_NAMES` or an equivalent split predicate that allows only:

```python
PHASE_FAMILY_PARENT_WORKFLOW_NAMES = frozenset(
    {
        "design_delta_parent_calls_work_item::run-parent-work-item",
    }
)
```

The accepted shapes are:

- `is_selected_phase_family_workflow()` returns true for the direct `lisp_frontend_design_delta/` family and for the single parent-call bridge fixture; or
- direct phase-family workflow classification and parent-call bridge classification use separate predicates, with all call sites preserving both paths where compatibility bridge/runtime context classification is required.

Do not remove parent-call bridge eligibility while keeping parent-call compile/smoke requirements in this plan. Add or tighten a regression assertion that the parent-call fixture's compatibility bridge inputs (`selection_bundle_path`, `manifest_path`, `architecture_bundle_path`, `progress_ledger_path`, and `run_state_path`) are not public authored inputs.

- [ ] **Step 3: Classify direct `PhaseCtx` leaves**

Ensure all flattened leaves rooted at a `PhaseCtx` parameter become `runtime_owned_context`, including imported/module-qualified `PhaseCtx` record names. The current `short_type_name()` shape should be preserved, but add a regression test if module-qualified names are missed.

Expected runtime context input names for `phase-ctx PhaseCtx`:

- `phase-ctx__run__run-id`
- `phase-ctx__run__state-root`
- `phase-ctx__run__artifact-root`
- `phase-ctx__phase-name`
- `phase-ctx__state-root`
- `phase-ctx__artifact-root`

- [ ] **Step 4: Classify selected compatibility bridge roots**

Keep the initial bridge root set exactly:

```python
{
    "selection_bundle_path",
    "manifest_path",
    "architecture_bundle_path",
    "progress_ledger_path",
    "run_state_path",
}
```

Allow bridge classification only when the root parameter name matches this set and the type is one of:

- `SelectionBundlePath`
- `ProgressLedger`
- `RunStatePath`
- `StateFile`
- `StateFileExisting`
- a `PathTypeRef` with `definition.under == "state"`

- [ ] **Step 5: Preserve generated write roots**

Do not reclassify `__write_root__...` inputs in `phase_family_boundary.py`. They should remain generated internal inputs with the existing `managed_write_root` reason from generated path allocation.

- [ ] **Step 6: Apply classification in both lowering routes**

In both `orchestrator/workflow_lisp/lowering/core.py` and `orchestrator/workflow_lisp/wcc/defunctionalize.py`, verify the sequence remains:

1. hidden/generated inputs are added to `authored_inputs`;
2. `apply_phase_family_boundary_classification(...)` updates `context.internal_generated_input_reasons` and discards from `context.authored_generated_inputs`;
3. `record_direct_entry_phase_context_binding(...)` records `PrivateExecContextBinding`;
4. finalized `WorkflowBoundaryProjection.generated_internal_inputs` includes the new reasons;
5. `LoweredWorkflow.compatibility_bridge_inputs` is derived from `internal_generated_input_reasons`.

Do not fork behavior between legacy and WCC routes.

- [ ] **Step 7: Run focused classification tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "design_delta_plan_phase_boundary or design_delta_work_item_boundary or runtime_context_inputs or compatibility_bridge" -q
```

Expected after this task: build-artifact classification tests pass or expose a remaining helper/call transport issue owned by Task 3.

## Task 3: Wire Hidden Phase Context Through Parent Calls And Private Helpers

**Files:**
- Modify: `orchestrator/workflow_lisp/lowering/workflow_calls.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_scope.py` or `orchestrator/workflow_lisp/phase.py` only if needed
- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py` only if WCC call lowering bypasses shared workflow-call helpers
- Modify: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Modify: `tests/test_workflow_lisp_wcc_characterization.py` and `tests/test_workflow_lisp_wcc_m4.py` only if route-specific regression coverage is needed

- [ ] **Step 1: Characterize missing parent-call binding**

The fixture `tests/fixtures/workflow_lisp/valid/design_delta_parent_calls_work_item.orc` calls imported `run-work-item` without passing `phase-ctx`. The selected behavior is that the parent call can omit `PhaseCtx` only when the imported callee has hidden context metadata and the caller route supports hidden context binding.

Add or tighten a test asserting:

- parent public inputs do not include `phase-ctx__...`;
- generated/private binding supplies the callee's `PhaseCtx`;
- missing metadata fails with `promoted_entry_hidden_context_metadata_missing` or `promoted_entry_hidden_phase_ctx_ambiguous`, not `workflow_boundary_type_invalid`.

- [ ] **Step 2: Reuse `_declare_runtime_context_hidden_inputs`**

In `orchestrator/workflow_lisp/lowering/workflow_calls.py`, keep using the existing `_declare_runtime_context_hidden_inputs(...)` path for omitted context parameters. If the selected WCC route does not populate `hidden_context_requirements` for `run-work-item`, fix the metadata producer rather than adding a call-site special case.

Expected binding record:

```python
PrivateExecContextBinding(
    binding_id="phase-ctx",
    source_param_name="phase-ctx",
    context_family="PhaseCtx",
    bridge_class="runtime_owned_context",
    generated_input_names=(...phase ctx leaves...),
    derived_phase_identity="work-item",
)
```

- [ ] **Step 3: Preserve explicit child calls with `:phase-ctx phase-ctx`**

The real `run-work-item` explicitly calls:

- `run-plan-phase` with `:phase-ctx phase-ctx`
- `implementation-phase` with `:phase-ctx phase-ctx`

Ensure those explicit record bindings are flattened as executable call bindings sourced from the runtime-owned ancestor context, not exposed as public helper workflow fields. If a private workflow generated for `route-blocked-implementation` carries phase context, it must receive hidden/generated fields or ancestor call bindings.

- [ ] **Step 4: Add a narrow diagnostic only if existing diagnostics are ambiguous**

Prefer existing diagnostics. Add a new diagnostic only if the implementation cannot clearly report the selected helper-boundary failure:

- `phase_family_boundary_context_unclassified`
- `phase_family_compatibility_bridge_unclassified`
- `phase_family_helper_context_boundary_invalid`

If added, include workflow name, parameter/generated field, source span, inferred authority class, and the next-owner tranche when the failure belongs to typed projection, resource transition, or parent drain.

- [ ] **Step 5: Run parent-call and WCC route tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "parent_call_work_item or work_item_candidate or wcc_ifexpr" -q
python -m pytest tests/test_workflow_lisp_wcc_m4.py tests/test_workflow_lisp_wcc_characterization.py -q
```

Expected after this task: parent-call work-item compiles or fails only on another documented later-tranche diagnostic, not phase boundary exposure or unsupported `IfExpr`.

## Task 4: Make The Required Lint Consume Classified Public Inputs

**Files:**
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/lints.py` only if rule metadata needs a clearer message
- Modify: `tests/test_workflow_lisp_diagnostics.py` only for regression coverage of unrelated public state-path failures
- Modify: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`

- [ ] **Step 1: Keep the lint strict by default**

`low_level_state_path_in_high_level_module` must continue to reject high-level workflows that expose public low-level `state/` paths.

Do not change `_type_ref_contains_low_level_state_path(...)` to blindly ignore all selected names or all records.

- [ ] **Step 2: Add a classified-public-boundary path for selected workflows**

In `_collect_stage3_required_lint_diagnostics(...)`, when the workflow is selected by `is_selected_phase_family_workflow(signature.name)`, derive or reuse the same boundary classification used by lowering and lint only the unclassified public-authored inputs and return type.

Implementation direction:

- derive flattened boundary fields from `signature.params`;
- classify fields with `classify_phase_family_boundary(...)`;
- treat classified runtime context and compatibility bridge fields as non-public for this lint;
- still diagnose any low-level state path fields that are not classified;
- still diagnose low-level state paths in return types unless another accepted contract owns them.

- [ ] **Step 3: Add a negative regression fixture if missing**

In `tests/test_workflow_lisp_diagnostics.py`, add or keep a small non-design-delta `.orc` workflow with a public `Path.state-existing` input. Assert it still emits `low_level_state_path_in_high_level_module`.

- [ ] **Step 4: Run lint-focused tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_diagnostics.py -k "low_level_state_path" -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "work_item_candidate or plan_phase_candidate" -q
```

Expected after this task: selected design-delta phase-family routes no longer fail the lint for classified private/compatibility fields; unrelated public `state/` inputs still fail.

## Task 5: Preserve Projection, Source Map, Loaded-Bundle, And Semantic IR Evidence

**Files:**
- Modify: `orchestrator/workflow_lisp/build.py` only if serialized artifact output misses data already present in bundles
- Modify: `orchestrator/workflow_lisp/source_map.py` only if generated/internal field origins are absent
- Modify: `orchestrator/workflow/semantic_ir.py` only if state-layout entries are missing
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_key_migrations.py`

- [ ] **Step 1: Assert loaded-bundle helper behavior**

For real `plan_phase.orc` and real `work_item.orc`, assert:

- `workflow_public_input_contracts(bundle)` excludes all `phase-ctx__...` leaves;
- `workflow_runtime_context_inputs(bundle)` includes all `phase-ctx__...` leaves;
- `workflow_boundary_projection(bundle).private_runtime_context_bindings` contains one `PhaseCtx` binding;
- `workflow_boundary_projection(bundle).private_compatibility_bridge_inputs` contains the selected bridge inputs for work-item.

- [ ] **Step 2: Assert build artifact serialization**

Read `workflow_boundary_projection.json` from `build_frontend_bundle(...)` and assert selected workflow payloads include:

```json
{
  "boundary": {
    "public_input_names": [],
    "private_runtime_context_bindings": [],
    "private_managed_write_root_inputs": [],
    "private_compatibility_bridge_inputs": []
  }
}
```

Use exact expected names for real workflows rather than empty arrays. The example above shows the shape only.

- [ ] **Step 3: Assert source-map provenance**

For each runtime context and compatibility bridge generated/internal input, assert the lowered workflow origin map has an entry in `origin_map.internal_input_spans` and not in `origin_map.authored_input_spans`.

Required fields:

- all `phase-ctx__...` runtime context leaves;
- `selection_bundle_path`;
- `manifest_path`;
- `architecture_bundle_path`;
- `progress_ledger_path`;
- `run_state_path`;
- generated `__write_root__...` inputs as managed write roots.

- [ ] **Step 4: Assert Semantic IR state-layout entries**

Inspect the compiled bundle's `semantic_ir` or use the existing Semantic IR helper pattern in the repo. Assert entries exist with:

- `layout_kind == "runtime_context_input"` for `phase-ctx__...` inputs;
- `layout_kind == "compatibility_bridge_input"` for retained YAML state/path bridges;
- source/provenance details point back to the selected workflow/module rather than a debug YAML view.

- [ ] **Step 5: Run artifact and migration regression tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "design_delta_work_item or design_delta_plan_phase_boundary or runtime_context_inputs or compatibility_bridge or public_inputs" -q
python -m pytest tests/test_workflow_lisp_key_migrations.py -k "runtime_context or public_inputs or promoted_entry" -q
```

Expected after this task: artifacts and helpers agree on the same public/private/compatibility split.

## Task 6: Convert Real Smoke Coverage And Guard Old Blockers

**Files:**
- Modify: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Modify: fixtures under `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/` only if runtime input defaults or artifact assertions need updates

- [ ] **Step 1: Keep old-blocker guards**

Keep `_assert_design_delta_work_item_candidate_post_ifexpr_boundary_failure(...)`, but rename if useful to `_assert_no_pre_tranche_3a_blockers(...)`.

It should assert absence of:

- `union_return_variant_ambiguous`
- `union_return_variant_incompatible`
- `proc_private_workflow_boundary_invalid`
- unsupported `IfExpr`

Add absence checks for:

- `low_level_state_path_in_high_level_module`
- `workflow_boundary_type_invalid`

Use this helper only in tests that intentionally characterize a remaining later-tranche failure.

- [ ] **Step 2: Assert complete route smoke**

For complete work-item route:

```python
workspace, state, provider_calls = _execute_design_delta_work_item_route(
    tmp_path / "completed",
    plan_variant="APPROVED",
    implementation_variant="COMPLETED",
    work_item_source="DRAFT_DESIGN_GAP",
)
assert state["status"] == "completed"
assert provider_calls[:2] == ["fake-plan-draft", "fake-plan-review"]
```

Assert route-appropriate output/report files based on the existing helper's written paths.

- [ ] **Step 3: Assert blocked recovery route smoke**

For implementation blocked route, assert:

- plan providers run;
- implementation execute provider runs;
- recovery classifier provider runs;
- terminal/recovery summary artifact exists;
- no provider/review route is invoked when not appropriate.

- [ ] **Step 4: Assert plan terminal blocked route smoke**

For plan blocked route, assert:

- plan providers run;
- implementation providers do not run;
- terminal blocked summary/report exists.

- [ ] **Step 5: Mirror smoke through parent-call work-item**

Repeat complete, blocked recovery, and terminal blocked routes through `_execute_design_delta_parent_call_work_item_route(...)`.

- [ ] **Step 6: Run feasibility band**

Run:

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "work_item_candidate or parent_call_work_item or plan_phase_candidate or implementation_phase_candidate or wcc_ifexpr" -q
```

Expected after this task: selected work-item and parent-call work-item routes produce positive compile/smoke evidence, while implementation-phase WCC evidence remains passing.

## Task 7: Documentation And Artifact Hygiene

**Files:**
- Modify docs only if implementation changes a lasting user-visible contract.
- Do not update global specs for transient implementation details.

- [ ] **Step 1: Decide whether docs changed**

If behavior only completes the already-approved architecture, no design/spec update is required beyond this execution evidence.

If behavior adds a new diagnostic, public helper, or lasting boundary class, update the narrowest lasting document:

- diagnostics catalog if required by local patterns;
- `docs/design/workflow_lisp_state_layout.md` if derivation responsibilities changed;
- `docs/lisp_workflow_drafting_guide.md` only for author-facing guidance.

- [ ] **Step 2: Do not update progress ledger manually unless the workflow requires it**

The consumed `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` is empty. Do not invent a completion event in the ledger unless the implementation workflow specifically owns ledger updates.

- [ ] **Step 3: Check output contract path**

Ensure `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-work-item/plan-phase/plan_path.txt` contains only:

```text
docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-phase-family-boundary-rehabilitation-post-ifexpr/execution_plan.md
```

## Final Verification

Run the deterministic command bundle from `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/check_commands.json`:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_key_migrations.py tests/test_workflow_lisp_wcc_characterization.py tests/test_workflow_lisp_wcc_m4.py -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "work_item_candidate or parent_call_work_item or plan_phase_candidate or implementation_phase_candidate or wcc_ifexpr" -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "design_delta_work_item or design_delta_plan_phase_boundary or runtime_context_inputs or compatibility_bridge or public_inputs" -q
python -m pytest tests/test_workflow_lisp_key_migrations.py -k "runtime_context or public_inputs or promoted_entry" -q
python -m pytest tests/test_workflow_lisp_wcc_m4.py tests/test_workflow_lisp_wcc_characterization.py -q
git diff --check
```

If implementation touches `orchestrator/workflow_lisp/compiler.py`, `orchestrator/workflow_lisp/lints.py`, or diagnostics coverage, also run:

```bash
python -m pytest tests/test_workflow_lisp_diagnostics.py -k "low_level_state_path" -q
```

Acceptance checklist:

- Implementation-phase parent-callable compile and smoke evidence still passes under WCC.
- Work-item route is still past returned-variant ambiguity, unsupported WCC `IfExpr`, and private-workflow export blockers.
- Real `plan_phase.orc` and `work_item.orc` no longer fail parent-callable compilation on `low_level_state_path_in_high_level_module`.
- Generated/private helper route carrying phase context no longer fails on `workflow_boundary_type_invalid`.
- Public boundary inspection excludes `PhaseCtx` leaves, generated write roots, and retained compatibility `state/` values.
- Boundary projection, source maps, loaded-bundle helpers, and Semantic IR identify runtime-owned context and compatibility bridge inputs.
- Any remaining failure is a documented later-tranche diagnostic, not boundary/path exposure or invalid phase-helper boundary type.
- No new hidden command glue, report parsing, pointer authority, resource transition, or parent-drain semantics are introduced.
