# Workflow Lisp Generic Core G5 Context Generalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Project rule override: do not create a worktree.

**Goal:** Implement Tranche G5 by making private executable context recognition structural and `RunCtx`-anchored, adding a `RunCtx`-only promoted-entry bootstrap lane with role-driven executor resolution, landing `std/context` as ordinary stdlib records, and proving the new lane with differential and acceptance fixtures without deleting any legacy name-keyed compatibility path.

**Architecture:** Reuse the existing promoted-entry, boundary-projection, and private-context binding pipeline instead of inventing a second route. Put structural classification and bootstrap planning in a new frontend-local module, make lowering record explicit per-input roles in `PrivateExecContextBinding.projection_hints`, and keep executor/runtime semantics generic: runtime derives only `RunCtx` anchor values while all domain context construction stays in Workflow Lisp `(record ...)` code. Validation consumers switch to structural-first classification with counted compatibility fallback, legacy `RunCtx`/`PhaseCtx` behavior stays byte-stable for existing bundles, and production Design Delta family modules remain untouched in this slice.

**Tech Stack:** Python, pytest, Workflow Lisp frontend and WCC schema 2, shared `orchestrator.workflow` bundle/executor surfaces, stdlib `.orc` modules, checked-in Workflow Lisp fixtures, and `python -m orchestrator compile|run`.

---

## Governing Context

Read before editing:

- `docs/index.md`
- `docs/work_definition_model.md`
- `docs/capability_status_matrix.md`
- `docs/design/README.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/plans/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/work_instructions.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
- `docs/design/workflow_lisp_generic_resource_context_core.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- `docs/design/workflow_lisp_runtime_migration_foundation.md`
- `docs/design/workflow_lisp_core_calculus_middle_end.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/plans/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/design-gaps/workflow-lisp-generic-core-g5-context-generalization/implementation_architecture.md`
- `state/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/drain/iterations/14/design-gap-architect/work_item_context.md`
- `state/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/progress_ledger.json`

## Current Checkout Facts

Use these as fixed assumptions. Do not rediscover them during implementation.

- `state/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/progress_ledger.json` is empty, so treat this as the first implementation pass for G5 rather than a follow-up patch.
- `orchestrator/workflow_lisp/phase.py` already encodes the six legacy private executable context families and already enforces a `RunCtx`-shaped anchor for each family; the new structural rule is a generalization of existing shape checks, not a new semantic category.
- `orchestrator/workflow/surface_ast.py` already gives `PrivateExecContextBinding` additive `projection_hints` and `required_capabilities` fields; use those for role metadata instead of widening durable runtime state.
- `orchestrator/workflow_lisp/lowering/workflow_calls.py` already owns promoted-entry hidden input declaration and compile-time defaults; the new lane must extend that codepath rather than bypass it.
- `orchestrator/workflow/executor.py` already bootstraps `RunCtx` and `PhaseCtx` by name; G5 replaces that as the primary route with schema-versioned role metadata while preserving the old name-keyed lane for legacy bundles only.
- `(record ...)` construction already exists in `orchestrator/workflow_lisp/expressions.py`, so `RunCtx`-only entry fixtures can build `DrainCtx` or `ExperimentCtx` in-language without compiler/runtime branches.
- G1, G3, and G4 are already landed and must be consumed unchanged. Do not reopen pure-expression, resource-transition, or materialized-view semantics in this slice.
- Production Design Delta family modules and boundary registries are out of scope. Use checked-in fixtures or temporary fixture modules for acceptance evidence instead of editing `workflows/library/lisp_frontend_design_delta/*.orc`.
- If implementation would require new durable runtime state beyond additive compile-output provenance, stop and raise a `specs/state.md` blocker instead of widening state silently.
- If acceptance fixtures hit a boundary-carriage diagnostic class explicitly owned by a G2A prerequisite tranche, stop and raise a blocker naming that tranche instead of broadening G5.

## File Map

Create:

- `orchestrator/workflow_lisp/context_classification.py`
- `orchestrator/workflow_lisp/stdlib_modules/std/context.orc`
- `tests/test_workflow_lisp_context_classification.py`
- `tests/fixtures/workflow_lisp/valid/context_generalization_experiment_ctx.orc`
- `tests/fixtures/workflow_lisp/valid/context_generalization_runctx_only_drain_entry.orc`
- `tests/fixtures/workflow_lisp/valid/context_generalization_std_context_import.orc`
- `tests/fixtures/workflow_lisp/invalid/context_generalization_anchorless_state_path.orc`
- `tests/fixtures/workflow_lisp/invalid/context_generalization_roleless_binding.orc`

Modify:

- `orchestrator/workflow_lisp/phase.py`
- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/workflow_lisp/typecheck_calls.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/phase_family_boundary.py`
- `orchestrator/workflow_lisp/lowering/workflow_calls.py`
- `orchestrator/workflow/executor.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_key_migrations.py`
- `tests/test_resume_command.py`
- `tests/test_workflow_lisp_drain_stdlib.py`
- `tests/test_workflow_lisp_resource_stdlib.py`
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_runtime_migration_foundation.md`
- `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
- `docs/capability_status_matrix.md`
- `docs/index.md`

Touch only if failing tests prove it is necessary:

- `orchestrator/workflow/surface_ast.py`
- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/workflow/semantic_ir.py`
- `orchestrator/workflow/executable_ir.py`
- `docs/design/workflow_lisp_state_layout.md`

Do not modify in this slice:

- `workflows/library/lisp_frontend_design_delta/drain.orc`
- `workflows/library/lisp_frontend_design_delta/work_item.orc`
- `workflows/library/lisp_frontend_design_delta/plan_phase.orc`
- `workflows/library/lisp_frontend_design_delta/implementation_phase.orc`
- phase/drain stdlib forms such as `with-phase`, `finalize-selected-item`, or `backlog-drain`
- any certified adapter or script under `workflows/library/scripts/**`
- `specs/dsl.md`
- `specs/state.md` unless the work is blocked on a real state-surface expansion

## Task 1: Characterize Current G5 Failure Modes

**Files:**

- Test: `tests/test_workflow_lisp_context_classification.py`
- Test: `tests/test_workflow_lisp_drain_stdlib.py`
- Test: `tests/test_workflow_lisp_resource_stdlib.py`
- Test: `tests/test_workflow_lisp_key_migrations.py`

- [ ] Run collection first so new test-module names are fixed before editing:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_resource_stdlib.py tests/test_workflow_lisp_key_migrations.py tests/test_resume_command.py -q
```

- [ ] Capture the current unsupported-bootstrap baseline for legacy name-bound families:

```bash
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -k "DrainCtx_hidden_binding_reports_unsupported_private_exec_bootstrap" -q
python -m pytest tests/test_workflow_lisp_resource_stdlib.py -k "ItemCtx_hidden_binding_reports_unsupported_private_exec_bootstrap" -q
python -m pytest tests/test_workflow_lisp_key_migrations.py -k "reserved_private_context_families_report_unsupported_bootstrap" -q
```

Expected before implementation: `DrainCtx`, `ItemCtx`, `SelectionCtx`, and `RecoveryCtx` still fail with `private_exec_context_bootstrap_unsupported`.

- [ ] Create `tests/test_workflow_lisp_context_classification.py` with failing coverage for the new module contract before writing implementation:
  - structural classification of canonical `RunCtx`, `PhaseCtx`, `ItemCtx`, `DrainCtx`, `SelectionCtx`, and `RecoveryCtx` shapes;
  - near-miss negatives: missing `run-id`, wrong `Path.under`, union-typed `run`, optional/list/map-wrapped anchors;
  - bootstrap planning for run-id, run state root, run artifact root, and compile-time-default fields;
  - zeroed fallback counters.

- [ ] Make the failing tests assert the future contract explicitly:
  - `classify_structural_private_exec_context(...)` returns a classification object with `anchors`, `derived_capabilities`, and `legacy_family`;
  - `structural_bootstrap_plan(...)` returns `None` for any roleless generated input;
  - fallback accounting is queryable and deterministic.

- [ ] Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_context_classification.py -q
python -m pytest tests/test_workflow_lisp_context_classification.py -q
```

Expected before implementation: collection succeeds; tests fail because the new module and helpers do not exist yet.

## Task 2: Add Structural Classification And Rewire Validation Consumers

**Files:**

- Create: `orchestrator/workflow_lisp/context_classification.py`
- Modify: `orchestrator/workflow_lisp/phase.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/type_env.py`
- Modify: `orchestrator/workflow_lisp/phase_family_boundary.py`
- Test: `tests/test_workflow_lisp_context_classification.py`
- Test: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] Implement `context_classification.py` as the sole structural-classification owner with:
  - `CONTEXT_BINDING_SCHEMA_VERSION = 1`;
  - `ContextAnchorKind` with implemented `RUN_CTX = "run_ctx"` and explicit deferred guards for `RESOURCE_HANDLE` and `RUNTIME_ALLOCATION`;
  - `ContextAnchor`;
  - `StructuralContextClassification`;
  - `ContextBootstrapPlan`;
  - `classify_structural_private_exec_context(type_ref)`;
  - `structural_bootstrap_plan(flattened_fields, classification)`;
  - `record_name_lane_fallback(...)` and `name_lane_fallback_counts()`.

- [ ] Move or delegate the existing `RunCtx` shape logic out of `phase.py` so `phase.py` keeps its public helpers but no longer owns the primary classification algorithm.

- [ ] Rewire `compiler._type_ref_contains_low_level_state_path(...)` to use structural classification first and only then fall back to `_ALLOWED_CONTEXT_RECORD_TYPES` with counted compatibility fallback. Preserve fail-closed behavior for anchor-free records.

- [ ] Rewire `type_env._record_refs_are_structural_contexts(...)` to use structural classification plus same-basename matching first, then the existing `_STRUCTURAL_CONTEXT_RECORD_NAMES` lane with counted fallback.

- [ ] Rewire `phase_family_boundary.classify_phase_family_boundary(...)` so runtime-owned context inputs are identified structurally and capability tags come from the classification/binding instead of `private_exec_context_capabilities("PhaseCtx")`.

- [ ] Keep every legacy name-keyed table in place and label it as G8-gated compatibility only. Do not delete any table or literal set in this task.

- [ ] Extend `tests/test_workflow_lisp_context_classification.py` so it proves:
  - structural classification is a superset of legacy family recognition on the shape corpus;
  - `legacy_family` agrees with the old lane when the old lane recognizes a shape;
  - fallback counters remain zero across the intended corpus;
  - the recorded `SelectionCtx` / `RecoveryCtx` low-level-state exemption widening is explicit and isolated.

- [ ] Add or update `tests/test_workflow_lisp_build_artifacts.py` assertions proving phase-family boundary reports stay unchanged for existing registered family workflows after the structural-first rewrite.

- [ ] Run:

```bash
python -m pytest tests/test_workflow_lisp_context_classification.py -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "phase_family_boundary or runtime_context_inputs" -q
```

Expected: structural classifier passes its corpus, fallback counts are zero, and existing boundary reports are unchanged.

## Task 3: Widen Promoted-Entry Metadata And Lowering

**Files:**

- Modify: `orchestrator/workflow_lisp/phase.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `orchestrator/workflow_lisp/typecheck_calls.py`
- Modify: `orchestrator/workflow_lisp/lowering/workflow_calls.py`
- Test: `tests/test_workflow_lisp_lowering.py`
- Test: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] Widen promoted-entry detection so a parameter is eligible when either:
  - the legacy family recognizer returns a known family; or
  - the new structural classifier returns a `RunCtx`-anchored classification.

- [ ] In `_declare_runtime_context_hidden_inputs(...)`, replace the pure name-whitelist gate with `structural_bootstrap_plan(...)` as the primary eligibility route. Preserve the old `private_exec_context_bootstrap_supported(...)` behavior only as labeled compatibility for legacy-family bundles without structural role hints.

- [ ] Record explicit role metadata in `PrivateExecContextBinding.projection_hints`:
  - `context_binding_schema_version = 1`;
  - `context_input_roles = {generated_input_name: role}`;
  - role strings exactly `run_anchor:run-id`, `run_anchor:state-root`, `run_anchor:artifact-root`, or `compile_time_default`.

- [ ] Preserve byte-stable legacy metadata for already-known shapes:
  - keep `context_family` equal to the legacy family name when one exists;
  - use `"RunCtxAnchored"` only for structurally recognized domain contexts unknown to the legacy family set;
  - keep `derived_phase_identity` behavior unchanged for `PhaseCtx`.

- [ ] Keep `_runtime_context_default_value(...)` unchanged for legacy family fields. For unknown structural contexts, only run-anchor fields derive runtime values automatically; any additional flattened field must already have a compile-time default or the compile must fail closed.

- [ ] Improve the existing `private_exec_context_bootstrap_unsupported` diagnostic so it names the first roleless/defaultless generated input rather than only the family name.

- [ ] Extend `tests/test_workflow_lisp_lowering.py` and `tests/test_workflow_lisp_build_artifacts.py` to assert:
  - a structurally recognized unknown context emits one `PrivateExecContextBinding`;
  - `projection_hints["context_binding_schema_version"] == 1`;
  - every generated hidden input is present in `context_input_roles`;
  - `generated_internal_inputs` still classify as `runtime_owned_context`;
  - origin spans stay internal, not public-authored.

- [ ] Run:

```bash
python -m pytest tests/test_workflow_lisp_lowering.py -k "private_exec_context" -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "private_exec_context or runtime_context_inputs" -q
```

Expected: promoted-entry lowering records structural role metadata without changing existing `PhaseCtx` bundle shape.

## Task 4: Add The Role-Driven Executor Lane And Resume Compatibility Proofs

**Files:**

- Modify: `orchestrator/workflow/executor.py`
- Test: `tests/test_workflow_lisp_key_migrations.py`
- Test: `tests/test_resume_command.py`
- Test: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] Make `_entry_runtime_context_bindings(...)` prefer the role-driven lane whenever `projection_hints` contains `context_input_roles` with schema version `1`.

- [ ] Implement role-driven resolution with exactly these mappings:
  - `run_anchor:run-id` -> `StateManager.run_id`
  - `run_anchor:state-root` -> `"state/run"`
  - `run_anchor:artifact-root` -> `"artifacts/run"`
  - `compile_time_default` -> the generated input contract default

- [ ] Keep `_private_exec_context_binding_value(...)` as the legacy name-keyed fallback for bundles that have no role hints. Do not make the legacy lane aware of new structural families.

- [ ] Make unknown `context_binding_schema_version` fail closed through the existing unsupported-binding surface rather than silently ignoring or reinterpreting the metadata.

- [ ] Update `_unsupported_private_exec_context_families(...)` so structurally recognized unknown contexts report the structural label when unsupported, keeping diagnostics actionable.

- [ ] Extend runtime tests to prove two compatibility properties:
  - the existing `PhaseCtx` promoted-entry fixture resolves byte-identical bound input values on the new role-driven lane and the old name-keyed lane;
  - a deliberately mutated bundle carrying an unknown schema version fails with `private_exec_context_bootstrap_unsupported` instead of partial binding.

- [ ] Use `tests/test_resume_command.py` to confirm the new lane remains resume-safe and does not change existing bound-input parity expectations for compiled entry bundles.

- [ ] Run:

```bash
python -m pytest tests/test_workflow_lisp_key_migrations.py -k "private_exec_context or context_generalization" -q
python -m pytest tests/test_resume_command.py -k "private_exec_context or context_generalization" -q
```

Expected: runtime binding remains byte-stable for existing `PhaseCtx` fixtures, and unknown-schema bundles fail closed.

## Task 5: Land `std/context` And Acceptance Fixtures

**Files:**

- Create: `orchestrator/workflow_lisp/stdlib_modules/std/context.orc`
- Create: `tests/fixtures/workflow_lisp/valid/context_generalization_experiment_ctx.orc`
- Create: `tests/fixtures/workflow_lisp/valid/context_generalization_runctx_only_drain_entry.orc`
- Create: `tests/fixtures/workflow_lisp/valid/context_generalization_std_context_import.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/context_generalization_anchorless_state_path.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/context_generalization_roleless_binding.orc`
- Modify: `tests/test_workflow_lisp_context_classification.py`
- Modify: `tests/test_workflow_lisp_drain_stdlib.py`
- Modify: `tests/test_workflow_lisp_resource_stdlib.py`
- Modify: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`

- [ ] Add `std/context.orc` with ordinary exported record definitions for `RunCtx`, `PhaseCtx`, `ItemCtx`, `DrainCtx`, `SelectionCtx`, and `RecoveryCtx`, matching the current validated shapes exactly. Do not add procedures, macros, or compiler special cases keyed to the module name.

- [ ] Add a focused import fixture proving an imported `std/context` `PhaseCtx` is accepted by existing name-validated consumers such as `build_phase_scope(...)`.

- [ ] Add the `ExperimentCtx` acceptance fixture as the proof of Section 14.4 / Scenario 25.4:
  - `ExperimentCtx` must be unknown to every name table;
  - it must classify structurally via a `RunCtx` anchor;
  - a promoted entry must receive private runtime binding with `context_input_roles`;
  - richer context state must be assembled in-language with `(record ...)`, not by runtime special cases.

- [ ] Add the `RunCtx`-only entry acceptance fixture:
  - the entry workflow binds only hidden `RunCtx` plus true public authored inputs;
  - it constructs `DrainCtx` in-language with `(record DrainCtx :run run ...)`;
  - an imported consumer workflow accepts that record;
  - build artifacts prove no public context input or public `state/` rooted context field leaks.

- [ ] Add negative fixtures proving:
  - a record with `state/` rooted fields but no `RunCtx` anchor still fails `low_level_state_path_in_high_level_module`;
  - a structurally classified context with at least one roleless/defaultless flattened field fails `private_exec_context_bootstrap_unsupported`.

- [ ] If either positive fixture fails on a boundary-carriage diagnostic class owned by a G2A prerequisite tranche, stop implementation and raise a blocker instead of working around the diagnostic inside G5.

- [ ] Extend `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py` with a narrow regression selector that proves existing Design Delta candidate compiles are no worse after structural context rewiring. Do not claim family migration or production-family bootstrap here.

- [ ] Run:

```bash
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -k "std_context or DrainCtx_hidden_binding" -q
python -m pytest tests/test_workflow_lisp_resource_stdlib.py -k "std_context or ItemCtx_hidden_binding" -q
python -m pytest tests/test_workflow_lisp_context_classification.py -k "experiment or runctx_only or anchorless or roleless" -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "implementation_phase_candidate_compiles_with_variant_and_review_loop or work_item_candidate_compiles_as_parent_callable_workflow or parent_call_work_item_compiles" -q
```

Expected: `ExperimentCtx` and `RunCtx`-only fixtures succeed on the WCC route, negatives fail closed, and existing family compile selectors stay green.

## Task 6: Land The Required Doc Deltas

**Files:**

- Modify: `docs/design/workflow_lisp_frontend_specification.md`
- Modify: `docs/design/workflow_lisp_runtime_migration_foundation.md`
- Modify: `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/index.md`
- Touch only if needed: `docs/design/workflow_lisp_state_layout.md`

- [ ] Update the baseline frontend spec context sections to say:
  - `RunCtx` is the only runtime-bootstrapped context;
  - domain contexts are library records over the generic core;
  - private executable context classification is structural and `RunCtx`-anchored;
  - name-keyed recognition remains compatibility-only pending G8 deletion evidence;
  - `std/context` is now an implemented stdlib surface.

- [ ] Update the target design with a narrow status note for G5:
  - `run_ctx` anchor kind implemented;
  - `resource_handle` and `runtime_allocation` anchors deferred pending typed runtime values.

- [ ] Update runtime-migration documentation only where necessary to describe the additive provenance keys (`context_binding_schema_version`, `context_input_roles`) and the fact that they are compile-output metadata, not durable runtime state.

- [ ] Update `docs/capability_status_matrix.md` and `docs/index.md` so future work routes to the new structural classification and `std/context` surfaces instead of rediscovering them.

- [ ] Do not change `specs/dsl.md` or `specs/state.md`. If the implementation cannot be described truthfully without those spec changes, stop and escalate.

## Task 7: Final Verification And Smoke Evidence

**Files:**

- Verification only

- [ ] Run collect-only for the new or renamed modules:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_context_classification.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_key_migrations.py tests/test_resume_command.py -q
```

- [ ] Run the focused verification sweep:

```bash
python -m pytest tests/test_workflow_lisp_context_classification.py -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "private_exec_context or runtime_context_inputs or phase_family_boundary" -q
python -m pytest tests/test_workflow_lisp_lowering.py -k "private_exec_context" -q
python -m pytest tests/test_workflow_lisp_key_migrations.py -k "private_exec_context or context_generalization" -q
python -m pytest tests/test_resume_command.py -k "private_exec_context or context_generalization" -q
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -k "std_context or DrainCtx_hidden_binding" -q
python -m pytest tests/test_workflow_lisp_resource_stdlib.py -k "std_context or ItemCtx_hidden_binding" -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "implementation_phase_candidate_compiles_with_variant_and_review_loop or work_item_candidate_compiles_as_parent_callable_workflow or parent_call_work_item_compiles" -q
```

- [ ] Run at least one real CLI smoke compile and one real CLI smoke run from the repo root:

```bash
python -m orchestrator compile tests/fixtures/workflow_lisp/valid/context_generalization_runctx_only_drain_entry.orc --entry-workflow entry --emit-semantic-ir .orchestrate/tmp/context_generalization_smoke/semantic_ir.json --emit-source-map .orchestrate/tmp/context_generalization_smoke/source_map.json
python -m orchestrator run tests/fixtures/workflow_lisp/valid/context_generalization_experiment_ctx.orc --entry-workflow entry --dry-run
```

- [ ] Treat the slice as complete only when all of the following are true:
  - fallback counters stay zero on the intended corpus;
  - no legacy name-keyed table or executor compatibility set was deleted;
  - `ExperimentCtx` and `RunCtx`-only fixtures pass without runtime special casing;
  - legacy `PhaseCtx` role-driven values are byte-equal to the old lane;
  - doc deltas and smoke commands produce fresh output from the repo root.

- [ ] Record in the implementation handoff:
  - the exact pytest selectors run and their results;
  - the exact `python -m orchestrator` smoke commands run;
  - any deferred blocker, with owning tranche if the blocker is outside G5.
