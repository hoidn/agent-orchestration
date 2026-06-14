# Workflow Lisp Private Runtime Value Flow C1 Typed Values As Prompt Inputs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Project rule override: do not create a worktree.

**Goal:** Land the bounded C1 Track C slice by replacing selected Workflow Lisp prompt-input materialization plumbing with executable-private `typed_prompt_inputs`, rendering those typed values in memory at provider prompt-composition time, emitting structured prompt-view evidence plus a `typed_prompt_input_report.json` compile artifact, and preserving the existing provider structured-output authority and prompt extern base-source behavior.

**Architecture:** Keep C1 additive over the shipped C0/U0 lanes and the current provider prompt contract. Workflow Lisp lowering continues to use the existing prompt extern base source (`asset_file` / `input_file`) for the authored prompt template, but C1-selected prompt rows stop generating producer-owned `materialize_artifacts` prompt-input steps and instead lower one executable-private `typed_prompt_inputs` lane that carries renderer descriptors, typed value refs, source-map lineage, and C0/U0 row ids through the shared surface/core/executable pipeline. Runtime prompt composition remains owned by `PromptComposer`: after the existing asset and workspace dependency injection steps, it resolves those typed value refs, renders deterministic bytes through `view_renderer.py`, injects the rendered blocks before `consumes`/output-contract suffixes, and writes one run-local evidence sidecar without changing `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, output-bundle validation, or public YAML authoring semantics. Build/parity consume the checked C0 manifest plus compiled prompt surfaces to emit one `typed_prompt_input_report.json` prerequisite artifact for the Design Delta family.

**Tech Stack:** Python 3, Workflow Lisp lowering, shared `orchestrator.workflow` surface/core/executable transport, `PromptComposer`, semantic IR/build artifacts, renderer registry in `orchestrator/workflow/view_renderer.py`, Design Delta migration inputs, pytest, `python -m orchestrator compile`

---

## Fixed Inputs

Treat these as implementation authority:

- `docs/index.md`
- `docs/design/README.md`
- `docs/capability_status_matrix.md`
- `docs/work_definition_model.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md`
- `docs/design/workflow_command_adapter_contract.md`
- `specs/providers.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-c1-typed-values-as-prompt-inputs/implementation_architecture.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-c0-rendering-census-and-renderer-seam-verification/implementation_architecture.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-u0-shared-census/implementation_architecture.md`
- `state/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/progress_ledger.json`
- `state/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/drain/iterations/8/design-gap-architect/work_item_context.md`

## Authority Reconciliation

Execute this plan against the accepted C1 implementation architecture and the current checkout, not against stale assumptions from pre-C0 planning.

- The selected C1 implementation architecture is authoritative for scope, schema ids, success evidence, diagnostic names, and the rule that typed prompt rendering is prompt-view-only rather than semantic authority.
- `docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md` owns the high-level C1 acceptance criteria: prompt rendering happens at the consumer seam, prompt-only renderings remain ephemeral by default, and producer-authored prompt-input files/materialization should disappear only for C1-selected rows.
- `docs/design/workflow_lisp_frontend_specification.md` remains authoritative for boundary-authority classes, generated source-map obligations, runtime-private transport, and the rule that frontends target shared workflow machinery rather than inventing a parallel prompt pipeline.
- `specs/providers.md` remains authoritative for provider prompt composition order, the distinction between prompt sources and semantic workflow inputs, `consumes` injection behavior, and output-bundle authority. C1 may add one typed prompt-input lane inside prompt composition, but it must preserve the normative base prompt source, `depends_on` injection, `consumes`, and output-contract suffix semantics.
- `docs/design/workflow_command_adapter_contract.md` forbids solving this slice with command glue, inline Python/shell, or certified adapters. Prompt rendering must stay runtime-native.
- The checked C0 manifest (`design_delta_parent_drain.consumer_rendering_census.json`) remains the inventory authority for which prompt rows are eligible. C1 consumes rows with `consumer_lane == "prompt_injection"` and `track_c_decision == "KEEP_TYPED"`; it does not invent a second prompt inventory.
- The existing `consumer_rendering_census_report.json` remains prerequisite evidence only. C1 adds a new compile artifact and runtime evidence lane; it does not reinterpret C0 as runtime completion.

## Current Checkout Facts

Use these as fixed starting assumptions unless a targeted failing test disproves one:

- `state/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/progress_ledger.json` is still empty.
- `docs/steering.md` is empty in this checkout and does not widen scope.
- `orchestrator/workflow_lisp/consumer_rendering_census.py` and the checked `design_delta_parent_drain.consumer_rendering_census.json` already exist. The relevant C1 prompt rows are `c0.plan_phase_prompt_draft` / `plan_phase.prompt.draft` and `c0.selector_prompt_select_next_work` / `selector.prompt.select_next_work`.
- `orchestrator/workflow_lisp/build.py` already loads the U0 and C0 checked inputs for `lisp_frontend_design_delta/drain::drain`, fingerprints them, emits `value_flow_census_report.json` and `consumer_rendering_census_report.json`, and fail-closes when those prerequisite reports drift.
- `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json` and `orchestrator/workflow_lisp/migration_parity.py` already require/consume `value_flow_census_report` and `consumer_rendering_census_report` for the Design Delta family.
- Runtime prompt composition is still split between `orchestrator/workflow/prompting.py` and `orchestrator/workflow/executor.py`. The current path is: read base prompt source, apply `asset_depends_on`, apply workspace `depends_on.inject`, apply `consumes` injection, append the output-contract suffix, optionally write `logs/<Step>.prompt.txt` in debug mode, then invoke the provider.
- The shared provider-step transport in `orchestrator/workflow/surface_ast.py`, `core_ast.py`, `elaboration.py`, `lowering.py`, `executable_ir.py`, `runtime_step.py`, and `semantic_ir.py` currently carries only `input_file`, `asset_file`, `depends_on`, `asset_depends_on`, `prompt_consumes`, `inject_consumes`, and `inject_output_contract`. There is no `typed_prompt_inputs` lane yet.
- Phase/provider lowering still routes prompt values through prompt-input materialization helpers:
  - `orchestrator/workflow_lisp/lowering/phase_scope.py::_build_phase_prompt_input_prelude`
  - `orchestrator/workflow_lisp/lowering/phase_scope.py::_build_phase_stdlib_prompt_input_prelude`
  - `orchestrator/workflow_lisp/lowering/phase_flow.py`
  - `orchestrator/workflow_lisp/lowering/effects.py::_lower_provider_result`
- Semantic IR prompt surfaces in `orchestrator/workflow/semantic_ir.py` currently record only provider name, base prompt source, `prompt_consumes`, and injection flags. They do not carry C1 renderer/value lineage.
- `tests/test_prompt_contract_injection.py` already owns focused prompt-composition unit coverage. `tests/test_workflow_lisp_lowering.py` already owns prompt-input prelude coverage. `tests/test_workflow_lisp_build_artifacts.py` and `tests/test_workflow_lisp_migration_parity.py` already have Design Delta helpers and compile-artifact assertions for U0/C0 lanes.

## Hard Scope Limits

Implement only this bounded C1 slice:

- one executable-private `typed_prompt_inputs` transport for selected Workflow Lisp provider steps;
- one runtime prompt-composition lane that renders typed values in memory through registered deterministic renderers;
- one run-local prompt-view evidence sidecar for rendered typed prompt inputs;
- one build-artifact lane that reconciles C0 prompt rows against compiled prompt surfaces and emits `typed_prompt_input_report.json`;
- parity-gate consumption of that emitted report as prerequisite compile evidence; and
- focused tests plus one Design Delta compile/smoke lane proving typed prompt values reach the provider without producer-authored prompt-input materialization.

Explicit non-goals:

- no C2 observability-summary generation, no C3 `:publish`, no C4 bridge metadata work, and no C5 render-cleanup/body rewrite beyond the selected C1 rows;
- no Track R checkpoint/resume changes;
- no provider or command structured-output authority changes, no output-bundle target rebinding, and no `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` semantics changes;
- no prompt extern manifest redesign: keep `design_delta_parent_drain.prompts.json` and prompt asset/input-file semantics intact as the base prompt source surface;
- no command adapters, inline Python/shell glue, or helper-script prompt rendering;
- no renderer-id/version changes, byte-format redesign, or generalized plugin system;
- no public YAML authoring surface for `typed_prompt_inputs`; and
- no migration-promotion decision or primary-surface flip.

## File Ownership

Create:

- `orchestrator/workflow_lisp/typed_prompt_inputs.py`
- `tests/test_workflow_lisp_typed_prompt_inputs.py`
- `tests/fixtures/workflow_lisp/valid/typed_prompt_input_phase.orc`

Modify:

- `orchestrator/workflow/prompting.py`
- `orchestrator/workflow/executor.py`
- `orchestrator/workflow/surface_ast.py`
- `orchestrator/workflow/core_ast.py`
- `orchestrator/workflow/elaboration.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/workflow/executable_ir.py`
- `orchestrator/workflow/runtime_step.py`
- `orchestrator/workflow/semantic_ir.py`
- `orchestrator/workflow_lisp/lowering/phase_scope.py`
- `orchestrator/workflow_lisp/lowering/phase_flow.py`
- `orchestrator/workflow_lisp/lowering/effects.py`
- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow_lisp/migration_parity.py`
- `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- `tests/test_prompt_contract_injection.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_semantic_ir.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_migration_parity.py`

Inspect and modify only if targeted failing tests prove it is required:

- `orchestrator/workflow_lisp/consumer_rendering_census.py`
- `orchestrator/workflow_lisp/value_flow_census.py`
- `orchestrator/workflow_lisp/workflows.py`
- `tests/test_workflow_surface_ast.py`
- `tests/test_workflow_ir_lowering.py`
- `tests/test_at70_prompt_audit.py`
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`

Do not modify in this slice unless verification proves the plan is incomplete:

- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.consumer_rendering_census.json`
- `workflows/library/lisp_frontend_design_delta/*.orc`
- `specs/`
- Track R or C2-C5 design docs

## Required Contract Decisions

These decisions are fixed for implementation and should not be reopened while coding:

- The lowered typed prompt-input schema id is exact: `workflow_lisp_typed_prompt_input.v1`.
- The runtime prompt-view evidence schema id is exact: `workflow_lisp_typed_prompt_input_evidence.v1`.
- The emitted compile report schema id is exact: `workflow_lisp_typed_prompt_input_report.v1`.
- The compile artifact path is exact: `.orchestrate/build/<hash>/typed_prompt_input_report.json`.
- The run-local evidence lane lives under `.orchestrate/runs/<run_id>/workflow_lisp/typed_prompt_inputs/`, keyed by runtime step identity rather than the debug-only `logs/<Step>.prompt.txt` lane.
- `typed_prompt_inputs` is an executable-private Workflow Lisp transport field. It may thread through shared surface/core/executable/runtime dataclasses so the validated bundle can execute it, but it must not become a new authored YAML contract or prompt extern manifest field.
- A lowered `typed_prompt_inputs` entry must carry, at minimum:
  - `schema_version`
  - `binding_name`
  - `renderer.renderer_id`
  - `renderer.renderer_version`
  - `renderer.accepted_shape`
  - one typed value reference or runtime-resolved typed binding identity
  - typed value type identity
  - `source_map_origin_key`
  - `u0_row_id`
  - `c0_row_id`
  - deterministic injection order metadata
- Supported C1 renderers in this tranche are the already-registered deterministic renderers in `orchestrator/workflow/view_renderer.py`. Start with the currently used `canonical-json` v1 and `posix-path-line` v1 shapes only; unknown renderer ids/versions or shape mismatches fail closed.
- Runtime prompt composition order stays compatible with `specs/providers.md`: keep the existing base prompt source plus `asset_depends_on` and `depends_on.inject` behavior, then inject typed prompt-input renderings, then existing `consumes` injection, then the output-contract suffix.
- C1 eligibility is exact: only checked C0 rows with `consumer_lane == "prompt_injection"` and `track_c_decision == "KEEP_TYPED"` participate. For the Design Delta family, that means the plan-phase draft prompt row and the selector prompt row.
- Suppression is row-scoped: when one C1 row is lowered to `typed_prompt_inputs`, the matching generated `materialize_artifacts` prompt-input value plus the matching `publishes` / `consumes` / `prompt_consumes` lane for that row must disappear. The base prompt extern file remains intact.
- Provider structured-output authority is unchanged. Rendered prompt fragments, prompt-view evidence JSON, prompt audits, and typed prompt-input reports must never satisfy `expected_outputs`, `output_bundle`, or `variant_output`.
- The new parity-artifact reason is exact: `typed_prompt_input_report` is `prerequisite_compile_evidence` with `parity_constrained: true`.
- Build/report diagnostics must use the C1 architecture names when applicable:
  - `typed_prompt_input_row_missing`
  - `typed_prompt_input_value_unavailable`
  - `typed_prompt_input_renderer_unknown`
  - `typed_prompt_input_renderer_shape_mismatch`
  - `typed_prompt_input_source_map_missing`
  - `typed_prompt_input_materialization_still_required`
  - `typed_prompt_input_rendered_view_used_as_state`
  - `typed_prompt_input_provider_authority_violation`

## Task 1: Lock The C1 Regression Surface Before Adding New Transport Or Runtime Behavior

**Files:**

- Create: `tests/test_workflow_lisp_typed_prompt_inputs.py`
- Create: `tests/fixtures/workflow_lisp/valid/typed_prompt_input_phase.orc`
- Modify: `tests/test_prompt_contract_injection.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_semantic_ir.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_migration_parity.py`

- [ ] Add `tests/test_workflow_lisp_typed_prompt_inputs.py` with focused coverage for:
  - one positive schema/normalization case for lowered `typed_prompt_inputs`;
  - one positive runtime evidence serialization case;
  - one negative test for missing C0/U0 lineage;
  - one negative test for unknown renderer id/version;
  - one negative test for renderer accepted-shape mismatch;
  - one negative test for non-JSON-like / non-path-string typed values;
  - one negative test proving rendered prompt evidence is not accepted as semantic state or output authority; and
  - one runtime smoke using `typed_prompt_input_phase.orc` plus a fake provider that captures the composed prompt and proves no producer-authored prompt-input file/materialization step is needed for the typed row.

- [ ] Add `typed_prompt_input_phase.orc` as the narrow proving fixture. It should:
  - exercise one provider-step path inside a phase-scope or stdlib-owned route that currently uses prompt-input materialization;
  - supply one typed record or pure projection prompt value that lowers to C1 transport;
  - keep the base prompt extern explicit; and
  - still require the provider to emit a structured bundle so output-authority tests can prove wrong-path bundles fail closed.

- [ ] Extend `tests/test_prompt_contract_injection.py` with prompt-composition failures/successes for:
  - deterministic typed prompt-input block rendering and ordering;
  - coexistence with `asset_depends_on`, `depends_on.inject`, `consumes`, and output-contract suffixes;
  - stable rendered-bytes digests; and
  - omission of typed prompt-input evidence when no typed rows are present.

- [ ] Extend `tests/test_workflow_lisp_lowering.py` with failing expectations for:
  - a C1-eligible provider step lowering one `typed_prompt_inputs` lane;
  - suppression of the matching legacy prompt-input prelude/materialize step for that row; and
  - retention of the legacy prelude for non-C1 or non-prompt rows so C1 stays bounded.

- [ ] Extend `tests/test_workflow_semantic_ir.py` with failing assertions that prompt surfaces expose additive typed prompt-input lineage and renderer metadata without leaking runtime-only evidence or changing other semantic authority fields.

- [ ] Extend `tests/test_workflow_lisp_build_artifacts.py` and `tests/test_workflow_lisp_migration_parity.py` with failing expectations for:
  - emitted `typed_prompt_input_report.json`;
  - family reconciliation against `c0.plan_phase_prompt_draft` and `c0.selector_prompt_select_next_work`;
  - fail-closed behavior when one selected row still needs legacy materialization;
  - fail-closed behavior when typed prompt metadata is missing from the prompt surface; and
  - parity-gate failure when `typed_prompt_input_report` is missing, unreadable, or non-passing.

- [ ] Run collection plus expected pre-implementation failures:

```bash
python -m pytest --collect-only \
  tests/test_workflow_lisp_typed_prompt_inputs.py \
  tests/test_prompt_contract_injection.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_semantic_ir.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_migration_parity.py -q
python -m pytest tests/test_workflow_lisp_typed_prompt_inputs.py -q
python -m pytest tests/test_prompt_contract_injection.py -k "typed_prompt_input" -q
python -m pytest tests/test_workflow_lisp_lowering.py -k "typed_prompt_input or prompt_input_prelude" -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "typed_prompt_input or design_delta_parent_drain" -q
python -m pytest tests/test_workflow_lisp_migration_parity.py -k "typed_prompt_input or design_delta_parent_drain" -q
```

Expected before implementation: collection passes once the new fixture/test file exists, while the new transport/runtime/build/parity assertions fail because no `typed_prompt_inputs` lane, runtime evidence sidecar, or `typed_prompt_input_report.json` artifact exists yet.

## Task 2: Add The C1 Helper Module And Thread Executable-Private Transport Through Shared Workflow Structures

**Files:**

- Create: `orchestrator/workflow_lisp/typed_prompt_inputs.py`
- Modify: `orchestrator/workflow/surface_ast.py`
- Modify: `orchestrator/workflow/core_ast.py`
- Modify: `orchestrator/workflow/elaboration.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/workflow/executable_ir.py`
- Modify: `orchestrator/workflow/runtime_step.py`
- Modify: `orchestrator/workflow/semantic_ir.py`
- Test: `tests/test_workflow_lisp_typed_prompt_inputs.py`
- Test: `tests/test_workflow_semantic_ir.py`

- [ ] Create `orchestrator/workflow_lisp/typed_prompt_inputs.py` as the owner of:
  - schema/version constants for lowered entries, runtime evidence, and compile report payloads;
  - normalized dataclass or dict helpers for `typed_prompt_inputs` entries;
  - deterministic typed-value digest helpers;
  - renderer-descriptor validation against `view_renderer.py`;
  - prompt-view evidence builders; and
  - compile-report builders that reconcile selected C0 rows against compiled prompt surfaces.

- [ ] Thread one executable-private `typed_prompt_inputs` field through the shared provider-step transport:
  - `SurfaceStep`
  - `CoreProviderStep`
  - surface-to-core elaboration/lowering
  - `ProviderStepConfig`
  - `RuntimeStep`
  - `SemanticPromptSurface`

- [ ] Keep that transport private:
  - do not add a new public prompt extern manifest shape;
  - do not add a new public YAML authoring feature;
  - if any shared loader/parser widening is needed, add a targeted validation guard or frontend-only injection path so authored YAML still cannot use the field directly.

- [ ] Extend `SemanticPromptSurface` so prompt surfaces can expose:
  - renderer descriptors;
  - typed value type identity;
  - source-map lineage;
  - `u0_row_id` / `c0_row_id`; and
  - deterministic in-step ordering metadata.

- [ ] Keep runtime-only evidence out of semantic IR:
  - no rendered prompt bytes;
  - no prompt-view evidence file paths;
  - no provider output claims.

- [ ] Run targeted tests after implementation:

```bash
python -m pytest tests/test_workflow_lisp_typed_prompt_inputs.py -k "schema or normalize or digest" -q
python -m pytest tests/test_workflow_semantic_ir.py -k "typed_prompt_input or prompt_surface" -q
```

Expected after Task 2: the repo can carry C1 metadata through the shared validated-bundle transport without exposing a new public YAML authoring surface, and semantic IR can explain the typed prompt-input lane additively.

## Task 3: Lower C1-Eligible Prompt Rows To Typed Prompt Inputs And Emit The Compile Report

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering/phase_scope.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_flow.py`
- Modify: `orchestrator/workflow_lisp/lowering/effects.py`
- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `orchestrator/workflow_lisp/migration_parity.py`
- Modify: `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- Test: `tests/test_workflow_lisp_lowering.py`
- Test: `tests/test_workflow_lisp_build_artifacts.py`
- Test: `tests/test_workflow_lisp_migration_parity.py`

- [ ] Add one C1 row-selection helper that consumes the already-loaded C0 manifest and returns the eligible prompt rows for the current workflow surface.

- [ ] Update `phase_scope.py`, `phase_flow.py`, and `effects.py` so C1-selected prompt rows:
  - lower to `typed_prompt_inputs` instead of prompt-input `materialize_artifacts` values;
  - preserve the base prompt extern step fields from `prompt_externs`;
  - suppress matching generated prompt-input `publishes` / `consumes` / `prompt_consumes` entries for the selected row only; and
  - keep the legacy prelude for all non-selected rows.

- [ ] Start with the smallest surface and generalize:
  - first prove one narrow fixture/provider-result path;
  - then cover the Design Delta plan-phase draft row;
  - then cover the selector row;
  - only after those pass should the helper treat all checked `prompt_injection`/`KEEP_TYPED` rows generically.

- [ ] Emit `typed_prompt_input_report.json` from `build.py` for `lisp_frontend_design_delta/drain::drain`. The report must reconcile:
  - the checked C0 row lineage;
  - compiled prompt surfaces from semantic IR;
  - lowered-workflow evidence that the matching legacy prompt-input materialization step is gone for selected rows; and
  - prompt source-map coverage for each selected row.

- [ ] Keep the report compile-scoped. It is prerequisite evidence about selected rows, lowered transport, and materialization retirement; it does not stand in for runtime rendered-bytes evidence.

- [ ] Update `migration_parity.py` and `parity_targets.json` so `design_delta_parent_drain` requires `typed_prompt_input_report` as compile evidence and fails cleanly when the artifact is absent, unreadable, or non-passing.

- [ ] Run targeted tests after implementation:

```bash
python -m pytest tests/test_workflow_lisp_lowering.py -k "typed_prompt_input or prompt_input_prelude" -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "typed_prompt_input or design_delta_parent_drain" -q
python -m pytest tests/test_workflow_lisp_migration_parity.py -k "typed_prompt_input or design_delta_parent_drain" -q
```

Expected after Task 3: selected C1 rows lower to executable-private typed prompt-input transport, the matching legacy prompt-input materialization disappears for those rows, and the Design Delta build emits one passing `typed_prompt_input_report.json`.

## Task 4: Render Typed Prompt Inputs At Runtime And Write Prompt-View Evidence

**Files:**

- Modify: `orchestrator/workflow/prompting.py`
- Modify: `orchestrator/workflow/executor.py`
- Test: `tests/test_prompt_contract_injection.py`
- Test: `tests/test_workflow_lisp_typed_prompt_inputs.py`

- [ ] Add one `PromptComposer` helper that:
  - accepts resolved typed prompt-input values plus their lowered metadata;
  - validates renderer id/version and accepted shape against `view_renderer.py`;
  - renders deterministic bytes in memory;
  - injects the rendered blocks after existing asset/workspace dependency injection and before `consumes`/output-contract injection; and
  - returns both the updated prompt text and one structured evidence payload per rendered typed prompt input.

- [ ] Keep prompt rendering view-only:
  - rendered bytes never touch workflow state as semantic authority;
  - the typed prompt-input evidence sidecar is diagnostic/runtime evidence only;
  - prompt audit text files remain debug-gated; C1 evidence sidecars are separate runtime evidence and should not depend on `--debug`.

- [ ] Extend `WorkflowExecutor` so provider execution:
  - resolves `typed_prompt_inputs` refs to concrete typed values before prompt composition;
  - writes one run-local evidence sidecar under `.orchestrate/runs/<run_id>/workflow_lisp/typed_prompt_inputs/`;
  - keeps the existing `_write_prompt_audit(...)` behavior unchanged; and
  - leaves `prepare_invocation(...)`, provider alias resolution, retries, timeout handling, managed jobs, and output-bundle validation unchanged.

- [ ] Add negative coverage proving provider structured-output authority is unchanged:
  - a provider that writes the declared bundle to the wrong path must still fail even when typed prompt rendering succeeds;
  - prompt evidence JSON must not appear in `_resolved_consumes`, artifact lineage, or output-contract validation.

- [ ] Run targeted tests after implementation:

```bash
python -m pytest tests/test_prompt_contract_injection.py -k "typed_prompt_input" -q
python -m pytest tests/test_workflow_lisp_typed_prompt_inputs.py -k "runtime_smoke or provider_authority" -q
```

Expected after Task 4: provider prompts can consume rendered typed values in memory, runtime evidence is recorded with renderer/value lineage, and provider output authority still depends only on declared bundle targets.

## Task 5: Re-Verify The C1 Slice And Run One Design Delta Compile/Smoke Lane

**Files:**

- Modify only if a failing verification proves necessity: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`

- [ ] Re-run collection for every touched test module:

```bash
python -m pytest --collect-only \
  tests/test_workflow_lisp_typed_prompt_inputs.py \
  tests/test_prompt_contract_injection.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_semantic_ir.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_migration_parity.py -q
```

- [ ] Re-run the narrow C1 selectors:

```bash
python -m pytest tests/test_workflow_lisp_typed_prompt_inputs.py -q
python -m pytest tests/test_prompt_contract_injection.py -k "typed_prompt_input" -q
python -m pytest tests/test_workflow_lisp_lowering.py -k "typed_prompt_input or prompt_input_prelude" -q
python -m pytest tests/test_workflow_semantic_ir.py -k "typed_prompt_input or prompt_surface" -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "typed_prompt_input or design_delta_parent_drain or consumer_rendering" -q
python -m pytest tests/test_workflow_lisp_migration_parity.py -k "typed_prompt_input or design_delta_parent_drain or consumer_rendering" -q
```

- [ ] Re-run one Design Delta compile plus smoke lane because this slice changes frontend lowering, prompt composition, and parity prerequisites:

```bash
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "design_delta_parent_drain_smokes_selected_item_completed_path or design_delta_parent_drain_smokes_selector_done_path" -q
```

- [ ] Confirm the final compile output contains `typed_prompt_input_report.json` beside the existing U0/C0 report lanes and that parity still classifies it as prerequisite compile evidence rather than promotion proof.

- [ ] Record in the implementation summary:
  - which files changed;
  - that `progress_ledger.json` remained unchanged unless explicitly updated elsewhere;
  - the exact pytest selectors and compile command run;
  - which C0 prompt rows are covered by C1;
  - whether any non-C1 rows intentionally retained legacy prompt-input materialization; and
  - that prompt extern base-source behavior stayed unchanged.

## Acceptance Checklist

- [ ] Selected C0 prompt rows lower to `workflow_lisp_typed_prompt_input.v1` transport entries instead of legacy prompt-input materialization.
- [ ] The base prompt extern surface (`asset_file` / `input_file`) remains intact and unchanged for the same provider steps.
- [ ] Selected rows no longer require generated prompt-input `materialize_artifacts` / `publishes` / `consumes` plumbing.
- [ ] Shared surface/core/executable/runtime transport can carry typed prompt-input metadata without exposing a new public YAML authoring feature.
- [ ] Semantic IR prompt surfaces expose typed prompt-input renderer/value/source-map lineage additively.
- [ ] Runtime prompt composition renders typed values after the existing asset/workspace injection stages and before `consumes` / output-contract suffixes.
- [ ] Runtime prompt-view evidence records renderer id/version, typed value identity, rendered-bytes digest, source-map lineage, and C0/U0 row ids in a run-local sidecar.
- [ ] Prompt-view evidence is never consumed as semantic state, artifact authority, or provider output authority.
- [ ] Provider structured-output validation still fails closed on missing or wrong-path bundles even when typed prompt rendering succeeds.
- [ ] `typed_prompt_input_report.json` is emitted for the Design Delta family and fails closed when a selected row still needs legacy materialization or lacks typed prompt-input metadata.
- [ ] `migration_parity.py` and `parity_targets.json` require `typed_prompt_input_report` as prerequisite compile evidence.
- [ ] The Design Delta compile/smoke lane still passes with the new C1 transport and evidence.

## Explicit Non-Goals

- Do not remove or redesign the base prompt extern manifest contract.
- Do not broaden renderer support beyond the existing deterministic registry unless a targeted failing test proves the selected C1 rows require it.
- Do not turn prompt-view evidence into build promotion evidence or semantic workflow outputs.
- Do not add C2-C5 behavior, Track R checkpoint work, or command-adapter glue.
- Do not change provider/command output-bundle authority, runtime output-path binding, or prompt audit debug semantics.
