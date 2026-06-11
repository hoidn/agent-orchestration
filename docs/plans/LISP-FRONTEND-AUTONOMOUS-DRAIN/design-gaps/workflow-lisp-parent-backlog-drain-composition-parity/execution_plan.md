# Workflow Lisp Parent Backlog-Drain Composition Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Project rule overrides generic skill defaults: do not create a worktree.

**Goal:** Add the first real Design Delta Drain parent `.orc` family route and strict parity evidence so parent-callable family progress is proven separately from leaf compile/smoke evidence.

**Architecture:** Promote the existing parent-callable work-item candidate from fixture-only proof into `workflows/library/lisp_frontend_design_delta/`, then add `drain.orc` as a typed WCC M4 parent loop over selector, design-gap, work-item, recovery, and terminal outcomes. Keep public boundaries clean with hidden/private context and compatibility-bridge labels, classify retained state/recovery helpers as certified adapters or resource-transition bridges, and teach migration parity to require parent-callable family evidence for the `design_delta_parent_drain` family.

**Tech Stack:** Workflow Lisp `.orc`, WCC M4 lowering/schema 2, `compile_stage3_entrypoint`, `WorkflowExecutor` fake-provider smokes, certified command-boundary manifests, `orchestrator.workflow_lisp.migration_parity`, pytest.

---

## Governing Context

Read before editing:

- `docs/index.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`, especially Sections 10A, 18, 19, 20, 21, 25, 27, 28, and 29
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/post_wcc_reconciliation_index.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parent-backlog-drain-composition-parity/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/2/design-gap-architect/work_item_context.md`

Important current-state facts:

- `workflows/library/lisp_frontend_design_delta/work_item.orc` currently exports only `classify-work-item-terminal` and `classify-blocked-implementation-recovery`.
- The parent-callable `run-work-item` candidate currently lives under `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/`.
- WCC `IfExpr` and phase-family boundary prerequisites are already complete for this selected work item. Do not redraft those prerequisites.
- This slice does not promote YAML primary replacement. `--require-promotable` must still fail unless complete promotable evidence exists.

## File Map

Modify:

- `workflows/library/lisp_frontend_design_delta/types.orc`: add missing candidate types from the fixture runtime root and parent-drain-only types such as `DrainState`, `DesignDeltaDrainAction`, boundary/artifact justification records, and parent terminal/status records if existing unions cannot represent them cleanly.
- `workflows/library/lisp_frontend_design_delta/work_item.orc`: promote the fixture `run-work-item` candidate into the library and keep existing classifier exports compatible.
- `workflows/library/lisp_frontend_design_delta/selector.orc`: add a pure/typed projection from `SelectorPublicResult` to the parent action union, or add a small exported helper if that keeps `drain.orc` simpler.
- `workflows/library/lisp_frontend_design_delta/design_gap_architect.orc`: expose any missing typed result needed by the parent for draft/validate route continuation without changing architect semantics.
- `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`: add `design_delta_parent_drain` as a separate family target.
- `orchestrator/workflow_lisp/migration_parity.py`: add optional parent-family readiness/evidence validation and route/schema freshness checks for family targets that declare them.
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`: add parent drain compile, boundary, and fake-provider smoke tests.
- `tests/test_workflow_lisp_build_artifacts.py`: add build artifact assertions for boundary projection, source-map/Semantic IR lineage, and certified adapter/resource-transition effects.
- `tests/test_workflow_lisp_drain_stdlib.py`: add family-idiom inventory tests if the parent route reuses `backlog-drain` forms or new pure projections.
- `tests/test_workflow_lisp_migration_parity.py`: add leaf-only rejection, parent-callable evidence role, route identity, and promotable/non-regressive gate tests.

Create:

- `workflows/library/lisp_frontend_design_delta/drain.orc`: real parent drain family entrypoint.
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json`
- Parent-specific fixtures under `tests/fixtures/workflow_lisp/valid/` only if the real library module needs controlled provider/command fixture assets.

Do not modify backlog queues or live run state.

## Task 1: Lock Parent-Family Failing Tests

**Files:**
- Modify: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_migration_parity.py`

- [ ] Add a compile helper `_compile_design_delta_parent_drain_entrypoint(tmp_path)` that compiles `workflows/library/lisp_frontend_design_delta/drain.orc` with `source_roots=(REPO_ROOT / "workflows" / "library",)`, WCC default route, `validate_shared=True`, and the same provider/prompt/command extern style used by the current work-item helpers.

- [ ] Add `test_design_delta_parent_drain_compiles_with_hidden_private_context`. Expected failure before implementation: missing `drain.orc` or unknown `run-work-item`. Final assertions:
  - validated bundle exists for `lisp_frontend_design_delta/drain::drain`;
  - public inputs exclude `phase-ctx`, `drain-ctx`, `selection_bundle_path`, `manifest_path`, `architecture_bundle_path`, `progress_ledger_path`, `run_state_path`, generated write roots, and raw `state_root`;
  - lowered workflow names include selector, design-gap architect, and `lisp_frontend_design_delta/work_item::run-work-item`;
  - lowering route is `wcc_m4` and schema version is `2` wherever the compile result exposes route metadata.

- [ ] Add `test_design_delta_parent_drain_records_boundary_and_artifact_justifications`. Assert every family workflow boundary in emitted boundary/projection metadata has a justification and every authored family artifact has one of these reasons: `public_boundary_identity`, `parity_comparison`, `legacy_consumption`, or `cross_run_durability`. Assert parity-only entries carry `parity_constrained`.

- [ ] Add `test_design_delta_parent_drain_resource_helpers_are_certified_or_declared`. Start with expected failure. Assert semantic parent-family helpers such as `materialize_lisp_frontend_work_item_inputs`, `classify_lisp_frontend_work_item_terminal`, `select_lisp_frontend_blocked_recovery_route`, `record_terminal_work_item`, `record_blocked_recovery_outcome`, `write_lisp_frontend_drain_status`, and `finalize_lisp_frontend_drain_summary` are either certified adapters or declared resource-transition bridges with behavior class, typed input/output, effects, fixtures, owner, and replacement path.

- [ ] Add parity tests that fail before implementation:
  - `test_design_delta_parent_drain_target_rejects_leaf_only_evidence_for_non_regressive`
  - `test_design_delta_parent_drain_target_rejects_leaf_only_evidence_for_promotable`
  - `test_design_delta_parent_drain_requires_route_schema_identity`
  These should construct report payloads by extending existing `_valid_report_payload()` helpers rather than shelling out.

- [ ] Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_migration_parity.py -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "design_delta_parent_drain" -q
python -m pytest tests/test_workflow_lisp_migration_parity.py -k "design_delta_parent_drain or leaf_only or route_schema" -q
```

Expected: collection passes; new behavioral tests fail for missing parent route or missing parity/readiness enforcement.

## Task 2: Promote The Work-Item Candidate Into The Library

**Files:**
- Modify: `workflows/library/lisp_frontend_design_delta/types.orc`
- Modify: `workflows/library/lisp_frontend_design_delta/work_item.orc`
- Modify: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`

- [ ] Copy the missing type contracts from `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/types.orc` into the library `types.orc` without deleting existing exported names. Required additions include `PlanDocTarget`, `ResolvedWorkItemInputs`, `WorkItemResult`, and `WorkItemTerminalReason` unless already present.

- [ ] Promote the fixture `run-work-item` implementation from `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/work_item.orc` into `workflows/library/lisp_frontend_design_delta/work_item.orc`. Preserve the existing exported classifier workflows and add `run-work-item` to exports.

- [ ] Keep private context hidden. `run-work-item` may accept `phase-ctx` internally, but tests must verify it is satisfied by hidden reusable-call binding when called from a parent and is not exposed as public generated state/path input.

- [ ] Convert raw semantic command calls in promoted code to certified adapter calls where the fixture already uses `:adapter`. For `record-terminal-work-item` and `record-blocked-recovery-outcome`, either add certified adapter bindings now or keep them as explicitly failing in Task 1 until Task 5 handles them. Do not treat stdout as semantic output.

- [ ] Update `test_design_delta_work_item_library_module_stays_closure_only` to the new contract. It should assert the library exports and lowers the classifier workflows plus `lisp_frontend_design_delta/work_item::run-work-item`, and it should keep the existing hidden-boundary/public-input assertions.

- [ ] Run:

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "work_item_library_module or parent_call_work_item or work_item_candidate" -q
```

Expected: work-item library compile and parent-call fixture tests pass without `low_level_state_path_in_high_level_module`, `workflow_boundary_type_invalid`, `proc_private_workflow_boundary_invalid`, or unsupported `IfExpr` diagnostics.

## Task 3: Add Parent Drain Types And Source

**Files:**
- Modify: `workflows/library/lisp_frontend_design_delta/types.orc`
- Modify: `workflows/library/lisp_frontend_design_delta/selector.orc`
- Create: `workflows/library/lisp_frontend_design_delta/drain.orc`
- Modify: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`

- [ ] Add parent-family records/unions in `types.orc`:
  - `DrainState`: loop status, iteration count, current run-state reference, item count, last summary/progress path, optional blocker/recovery reason.
  - `DesignDeltaDrainAction`: variants for selected work item, design gap, prerequisite/recovery if implemented in this slice, done, blocked, and exhausted.
  - `BoundaryJustification` and `ArtifactJustification`: boundary/artifact id, reason, route, schema version, readiness label, `parity_constrained` bool.
  - Reuse `DrainResult` unless it cannot carry typed parity-comparable terminal data; if extended, keep existing `DONE`, `BLOCKED`, and `EXHAUSTED` variants compatible.

- [ ] Add an exported pure projection in `selector.orc`, for example `project-selector-action`, from `SelectorPublicResult` to `DesignDeltaDrainAction`. It may branch on typed provider result fields, but it must not read the `selection_bundle_path` as pointer authority.

- [ ] Implement `drain.orc`:
  - import `select-next-work` and `project-selector-action`;
  - import `draft-design-gap-architecture` and `validate-design-gap-architecture`;
  - import `run-work-item`;
  - construct `DrainCtx`, `SelectionCtx`, `ItemCtx`, and `RecoveryCtx` as scoped data or pure projections;
  - use `loop`/`recur` or the existing `backlog-drain` surface to carry `DrainState`;
  - call `run-work-item` for selected/prepared item routes;
  - call the architect route for `DRAFT_DESIGN_GAP` and then transition into retry/prepared work state where feasible;
  - return typed `DrainResult` variants for normal done, blocked, and exhausted paths.

- [ ] Keep the first slice bounded. It is acceptable to smoke one selected-item path and one blocked/recovery path, while prerequisite/design-gap paths compile and have typed branches plus explicit TODO evidence labels if full runtime smoke would require unrelated workflow mechanics.

- [ ] Run:

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "design_delta_parent_drain_compiles or design_delta_parent_drain_records_boundary" -q
```

Expected: parent route compiles and shared-validates with hidden private context and WCC route/schema evidence.

## Task 4: Add Parent Drain Runtime Smoke Coverage

**Files:**
- Modify: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Create fixtures under `tests/fixtures/workflow_lisp/valid/` only if needed.

- [ ] Extend the fake provider/executor helpers used by `_execute_design_delta_work_item_route` so they can also drive `lisp_frontend_design_delta/drain::drain`.

- [ ] Add `test_design_delta_parent_drain_smokes_selected_item_completed_path`. The smoke should select one work item, execute plan and implementation phases with fake providers, record the declared item/resource transition, update loop state, and return `DrainResult.DONE` or the target terminal variant for one-item completion.

- [ ] Add `test_design_delta_parent_drain_smokes_blocked_recovery_path`. The smoke should select one item, drive implementation `BLOCKED`, run blocked-recovery classification, record a declared recovery transition or certified adapter bridge, and return a typed blocked/recovery terminal or loop-continuation result depending on the implemented bounded route.

- [ ] Assert control flow is not decided by reading a ledger, pointer file, markdown report, stdout payload, or debug YAML as semantic state. The test can inspect lowered metadata/semantic IR and the fake command/provider call order.

- [ ] Run:

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "design_delta_parent_drain_smokes" -q
```

Expected: selected item and blocked/recovery smokes pass with deterministic fake provider calls and typed workflow outputs.

## Task 5: Certify Parent-Family Command/Resource Bridges

**Files:**
- Create: `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json`
- Modify: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: any narrow command-boundary parsing code only if existing manifest support cannot express the required metadata.

- [ ] Add certified adapter manifest entries for retained semantic helpers. Minimum entries:
  - `materialize_lisp_frontend_work_item_inputs`: `typed_projection`, owner `lisp_frontend_design_delta/work_item`, replacement `SelectionCtx + ItemCtx private bootstrap + typed projection`.
  - `classify_lisp_frontend_work_item_terminal`: `outcome_finalization`, owner `lisp_frontend_design_delta/work_item`, replacement `typed implementation terminal union`.
  - `select_lisp_frontend_blocked_recovery_route`: `outcome_finalization`, owner `lisp_frontend_design_delta/work_item`, replacement `typed BlockedRecoveryDecision projection`.
  - `record_terminal_work_item`: `resource_transition` and `ledger_update`, owner `lisp_frontend_design_delta/work_item`, replacement `runtime-native selected-item transition`.
  - `record_blocked_recovery_outcome`: `resource_transition` and `ledger_update`, owner `lisp_frontend_design_delta/work_item`, replacement `runtime-native blocked-recovery transition`.
  - parent drain summary/status helpers, if called by `drain.orc`, with `outcome_finalization` or `ledger_update` behavior as appropriate.

- [ ] Each entry must include typed inputs, output type, effects, path-safety rule, source-map behavior, positive fixture ids, negative fixture ids, error codes, owner module, and replacement path. Do not add broad repo-wide lint enforcement in this slice.

- [ ] Add build artifact assertions that the command boundaries appear in Semantic IR/source-map output as certified adapter/resource-transition effects, not opaque command calls.

- [ ] Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "design_delta_parent_drain or command_boundary_lineage or compatibility_bridge or resource_transition" -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "resource_helpers_are_certified or design_delta_parent_drain_smokes" -q
```

Expected: all retained semantic helpers are classified or certified; negative fixtures fail closed where manifests are incomplete.

## Task 6: Add Parent-Drain Extern Files And Parity Target

**Files:**
- Create: `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json`
- Create: `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json`
- Create: `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json`
- Modify: `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- Modify: `tests/test_workflow_lisp_migration_parity.py`

- [ ] Add provider externs for selector, architect draft, plan draft/review/fix, implementation execute/review/fix, and work-item recovery classifier. Use the same logical names already referenced by the `.orc` modules.

- [ ] Add prompt externs for selector, architect, plan, implementation, and work-item recovery prompts. Reuse existing `workflows/library/prompts/...` paths where present.

- [ ] Add `design_delta_parent_drain` to `parity_targets.json`:

```json
{
  "workflow_family": "design_delta_parent_drain",
  "candidate": "workflows/library/lisp_frontend_design_delta/drain.orc",
  "yaml_primary": "workflows/examples/lisp_frontend_design_delta_drain.yaml",
  "entry_workflow": "lisp_frontend_design_delta/drain::drain",
  "provider_externs_file": "workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json",
  "prompt_externs_file": "workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json",
  "command_boundaries_file": "workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json",
  "readiness_label": "parent_callable_candidate",
  "lowering_route": "wcc_m4",
  "lowering_schema_version": 2,
  "required_family_evidence_roles": [
    "parent_callable_compile",
    "parent_callable_smoke",
    "resource_transition_parity",
    "public_private_boundary_parity",
    "route_identity"
  ],
  "promotion_eligibility": {
    "eligible_for_primary_surface": false,
    "blocked_reason": "parent-family candidate only; YAML primary replacement requires strict promotable family evidence"
  }
}
```

Include the existing required `baseline_characterization`, `accepted_differences`, `deprecated_yaml_mechanics`, `compile_artifacts`, and `evidence_commands` fields following current manifest schema.

- [ ] Run:

```bash
python -m pytest tests/test_workflow_lisp_migration_parity.py -k "load_parity_targets or design_delta_parent_drain" -q
```

Expected: target manifest loads, and the target remains non-promotable until strict evidence is complete.

## Task 7: Enforce Parent-Callable Evidence In Migration Parity

**Files:**
- Modify: `orchestrator/workflow_lisp/migration_parity.py`
- Modify: `tests/test_workflow_lisp_migration_parity.py`

- [ ] Extend `ParityTarget` to preserve optional fields: `readiness_label`, `lowering_route`, `lowering_schema_version`, and `required_family_evidence_roles`.

- [ ] Extend report validation to accept and validate parent-family sections when the selected target declares `required_family_evidence_roles`:
  - `readiness_label` must match the target.
  - `route_identity.lowering_route` and `route_identity.lowering_schema_version` must match the target.
  - parent evidence must include all required family roles with `status: pass`.
  - route-mismatched or missing parent evidence makes `evidence_complete=false`.

- [ ] Ensure `compute_non_regressive()` cannot return true for `design_delta_parent_drain` when evidence only proves leaves. Do this by checking family evidence through target-aware gate validation rather than making every existing target require parent evidence.

- [ ] Ensure `render_gate_evaluation(..., gate_mode="require_promotable")` still fails for this target while `eligible_for_primary_surface=false`, even if parent-callable non-regressive evidence is complete.

- [ ] Keep existing reports/targets backwards-compatible unless they declare the new family evidence fields.

- [ ] Run:

```bash
python -m pytest tests/test_workflow_lisp_migration_parity.py -k "design_delta_parent_drain or leaf_only or route_identity or non_regressive or promotable" -q
```

Expected: leaf-only evidence fails selected-family strict gates; complete parent-callable but ineligible evidence can pass `--require-non-regressive` and fail `--require-promotable`; route/schema mismatch is stale evidence.

## Task 8: Build Artifact And Family-Idiom Evidence

**Files:**
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_drain_stdlib.py`
- Modify: `workflows/library/lisp_frontend_design_delta/drain.orc` if tests reveal YAML-shaped glue.

- [ ] Add artifact inspection for `drain.orc` build output:
  - `workflow_boundary_projection.json` records public/private split and generated path allocations.
  - `semantic_ir.json` records generated context/path provenance and command/resource/projection effects.
  - `source_map.json` includes parent loop, branch, call, context projection, adapter/resource transition, and generated path entries.

- [ ] Add family-idiom assertions:
  - loop control is carried in `DrainState`;
  - phase-to-phase interchange is typed values unless artifact justification records say otherwise;
  - interior context derivation lowers as `pure_projection`;
  - parity-only boundaries/artifacts are labeled `parity_constrained`;
  - no pointer/report/stdout/debug-YAML authority drives parent control flow.

- [ ] Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "design_delta_parent_drain or source_map or semantic_ir or workflow_boundary_projection" -q
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -k "backlog_drain or family_idiom or pure_projection" -q
```

Expected: build artifacts expose the parent-family authority and effect graph required by the target design.

## Task 9: End-To-End CLI Smoke

**Files:**
- No new files unless the command exposes missing extern/manifest issues.

- [ ] Run compile through the CLI with explicit extern files:

```bash
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc \
  --entry-workflow lisp_frontend_design_delta/drain::drain \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

Expected: compile exits 0 and emits core workflow AST, semantic IR, source map, executable IR, runtime plan, diagnostics, and workflow boundary projection artifacts.

- [ ] If fake-provider runtime inputs are available through CLI fixtures, run a dry-run or fake-provider smoke for selected-item and blocked/recovery paths. If not, document why pytest smokes are the bounded integration evidence for this slice.

## Task 10: Final Verification

**Files:**
- All files touched above.

- [ ] Run collect-only for changed/added tests:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_migration_parity.py -q
```

- [ ] Run focused checks:

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "design_delta_parent_call_work_item or design_delta_parent_drain or work_item_library_module" -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "design_delta_work_item or design_delta_parent_drain or command_boundary_lineage or compatibility_bridge or resource_transition" -q
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -k "backlog_drain or family_idiom or pure_projection" -q
python -m pytest tests/test_workflow_lisp_migration_parity.py -k "promotable or non_regressive or leaf_only or design_delta_parent_drain or route_identity" -q
```

- [ ] Run a wider Workflow Lisp regression band if focused checks pass:

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_migration_parity.py -q
```

- [ ] Run repository hygiene:

```bash
git diff --check
```

Expected: all commands pass. If any test remains intentionally skipped or CLI smoke is not runnable, record the exact reason and the substitute verification evidence in the implementation summary.

## Completion Criteria

The work is complete when:

- `workflows/library/lisp_frontend_design_delta/drain.orc` compiles, shared-validates, and smokes at least a selected-item path and a blocked/recovery path.
- `workflows/library/lisp_frontend_design_delta/work_item.orc` exports the parent-callable `run-work-item` route, not only classifier helpers.
- Parent public inputs hide generated/private context and YAML-era state/write-root paths.
- Boundary and artifact justifications exist, and parity-only shapes are labeled `parity_constrained`.
- Retained parent-family semantic helpers are certified adapters or declared resource-transition bridges with visible effects.
- Migration parity distinguishes leaf evidence from parent-callable family evidence and rejects leaf-only reports for strict family gates.
- `design_delta_parent_drain` is a separate parity target and remains non-promotable until promotable evidence is intentionally produced.
