# Semantic Workflow IR Shared Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the bounded shared `SemanticWorkflowIR` contract so validated workflows carry one semantic-meaning bundle surface, compiled Workflow Lisp builds emit `semantic_ir.json`, and build/explain/coverage surfaces stop treating `semantic_ir` as deferred while `core_workflow_ast` remains deferred.

**Architecture:** Keep semantic meaning shared under `orchestrator/workflow/` and keep Workflow Lisp-specific artifact emission under `orchestrator/workflow_lisp/`. Derive Semantic IR from validated `SurfaceWorkflow`, `ExecutableWorkflow`, `WorkflowStateProjection`, imported `LoadedWorkflowBundle` edges, and existing provenance metadata; do not derive it from frontend-only syntax, debug YAML, runtime logs, report parsing, or pointer files.

**Tech Stack:** Python dataclasses, `orchestrator/workflow`, `orchestrator/workflow_lisp`, existing loader/build/explain/runtime-observability surfaces, pytest, and the checked-in Workflow Lisp CLI fixtures under `tests/fixtures/workflow_lisp/`.

---

## Fixed Inputs

Treat these as implementation authority:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `0. Prerequisites, Boundaries, And Missing Internal Specs`
  - `45. Core Workflow AST`
  - `46. Validated Core Workflow AST`
  - `47. Semantic IR`
  - `48. Executable IR`
  - `59. Validation Sequence`
  - `64. Snapshot Validation`
  - `65. Pointer Authority Validation`
  - `66. Report-Authority Validation`
  - `72. Lowering Errors`
  - `74. Source Map Requirements`
  - `76. Build Artifacts`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `6. Lowering Contract`
  - `9. Source Spans And Diagnostics`
  - `10. Validation`
  - `14. Implementation Stages`
- `docs/design/workflow_lisp_semantic_workflow_ir.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/semantic-workflow-ir-shared-contract/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-full-restart-20260523T081550Z/iterations/0/design-gap-architect/work_item_context.md`

## Current Repo Baseline

Assume this exact starting point:

- `docs/steering.md` is empty in this checkout and does not widen scope.
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` currently has no events, so do not infer partial implementation from ledger state.
- There is no `orchestrator/workflow/semantic_ir.py` module yet.
- `orchestrator/workflow/loaded_bundle.py` exposes `surface`, `ir`, `projection`, `runtime_plan`, `imports`, and `provenance`, but no semantic-IR surface or helper.
- `orchestrator/workflow/lowering.py::build_loaded_workflow_bundle(...)` currently derives only `ir`, `projection`, and `runtime_plan` before constructing `LoadedWorkflowBundle`.
- `orchestrator/workflow_lisp/build.py` writes `executable_ir.json`, `runtime_plan.json`, `source_map.json`, and `workflow_boundary_projection.json`, but not `semantic_ir.json`.
- `orchestrator/workflow_lisp/build.py` recreates a selected `LoadedWorkflowBundle` after provenance/runtime-plan enrichment, so any new bundle field must be threaded through that second construction site too.
- `orchestrator/workflow_lisp/source_map.py` still reports `semantic_ir` coverage as `deferred_shared_contract`.
- `orchestrator/cli/commands/explain.py` still prints `Deferred artifacts: core_workflow_ast, semantic_ir`.
- `tests/test_workflow_semantic_ir.py` does not exist yet.
- Existing tests in `tests/test_workflow_lisp_build_artifacts.py` and `tests/test_runtime_observability.py` still assert that `semantic_ir` is deferred.

## Hard Scope Limits

Implement only the selected `semantic-workflow-ir-shared-contract` slice:

- one shared `SemanticWorkflowIR` schema, builder, validator, and serializer under `orchestrator/workflow/`;
- shared bundle integration so YAML-loaded and Workflow Lisp-compiled bundles both carry `semantic_ir`;
- one deterministic serialized `semantic_ir.json` artifact for compiled `.orc` entrypoints;
- explain/build/source-map/runtime-observability surface updates so `semantic_ir` is emitted and covered;
- deterministic `semantic_ir_invalid` failures with structured subject refs when available.

Explicit non-goals:

- no fabricated `core_workflow_ast.json` artifact and no fake Core AST contract just to mirror Semantic IR;
- no new Workflow Lisp language forms, stdlib changes, parser/macro/module/procedure work, or runtime executor redesign;
- no new command adapters, no shell-text inspection, no report parsing as semantic authority, and no pointer-file recovery as workflow meaning;
- no source-map schema redesign beyond changing the `semantic_ir` coverage status and recording bridge facts already supported by existing provenance;
- no second semantic-meaning authority surface outside the shared loaded bundle.

## Non-Negotiable Contracts

Keep these contracts fixed during execution:

- `SurfaceWorkflow` remains the validated authored-semantics authority.
- `ExecutableWorkflow` remains the execution authority.
- `WorkflowStateProjection` remains the compatibility/resume authority.
- `SemanticWorkflowIR` is a shared semantic index between validated workflow meaning and executable/runtime views; it is not a frontend-only dump and not a second executor.
- Semantic IR must derive only from validated shared structures plus existing provenance metadata:
  `surface`,
  `ir`,
  `projection`,
  `imports`,
  `provenance`,
  and existing command-boundary/source-map metadata.
- Command entries in Semantic IR record only declared metadata:
  boundary kind,
  stable tool/adapter name,
  output-validation surface,
  and source-map behavior when declared.
- Source spans remain authoritative in `source_map.json`; Semantic IR may reference origin keys and `ValidationSubjectRef` bindings, but must not duplicate full source-map payloads.
- `core_workflow_ast` stays deferred in manifests, explain output, and coverage metadata.
- Serialization must be deterministic and JSON-compatible. Use a dedicated schema constant such as `WORKFLOW_SEMANTIC_IR_SCHEMA_VERSION = "workflow_semantic_ir.v1"`.

## File Ownership

Create:

- `orchestrator/workflow/semantic_ir.py`
- `tests/test_workflow_semantic_ir.py`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/semantic-workflow-ir-shared-contract/execution_plan.md` (this file)

Modify:

- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow_lisp/source_map.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/cli/commands/explain.py`
- `tests/test_workflow_ir_lowering.py`
- `tests/test_loader_validation.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_cli.py`
- `tests/test_workflow_lisp_diagnostics.py`
- `tests/test_runtime_observability.py`

Modify only if a focused failing test proves the bridge is required:

- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/validation.py`
- `tests/workflow_bundle_helpers.py`

Do not widen ownership into parser, macro, module, stdlib, queue, state-manager, or runtime executor code unless a targeted failing test shows this slice cannot be completed without a narrow bridge change.

## Required Semantic IR Shape

Implement the initial shared contract in one module, even if some nested dataclasses are lightweight:

- `SemanticWorkflowIR`
  - `schema_version`
  - `workflows`
  - `types`
  - `contracts`
  - `refs`
  - `effects`
  - `proofs`
  - `state_layout`
  - `source_map`
- `SemanticWorkflow`
  - workflow name
  - typed input/output contract ids
  - authored-order statement ids
  - imported/local call edges
  - provider prompt-contract surfaces
  - command-boundary metadata
  - publication plan
  - executable/projection bridge metadata
- supporting entries kept inside `semantic_ir.py`
  - contract/type catalog entries
  - ref/effect/proof/state-layout entries
  - source-map bridge entries
  - statement bridge entries

Implementation rules:

- Use stable ids derived from validated workflow names, step ids, artifact names, output names, imported aliases, and executable node ids.
- Build catalog content from existing validated surfaces:
  `SurfaceWorkflow.inputs`,
  `SurfaceWorkflow.outputs`,
  step configs,
  `ExecutableWorkflow.nodes`,
  `WorkflowRuntimePlan`,
  `WorkflowStateProjection`,
  imported bundles,
  and compiled-frontend provenance.
- Record variant-proof surfaces only when the validated workflow already exposes them.
- Record snapshot/layout surfaces only from validated snapshot and projection/runtime-plan metadata.
- For YAML workflows, allow an empty `source_map` bridge while still populating semantic contracts, refs, effects, proofs, and state layout.

## Task 1: Add The Shared Semantic IR Contract And Bundle Integration

**Files:**

- Create: `orchestrator/workflow/semantic_ir.py`
- Modify: `orchestrator/workflow/loaded_bundle.py`
- Modify: `orchestrator/workflow/lowering.py`
- Create: `tests/test_workflow_semantic_ir.py`
- Modify: `tests/test_workflow_ir_lowering.py`
- Modify: `tests/test_loader_validation.py`

- [ ] **Step 1: Add failing shared-contract tests before implementing the module**

Create `tests/test_workflow_semantic_ir.py` and extend the existing bundle tests so the shared surface is locked down first. Cover at least these cases:

- YAML-loaded workflows expose `bundle.semantic_ir`.
- `workflow_semantic_ir(bundle)` returns the shared object and `None` for non-bundles.
- `semantic_ir.schema_version == "workflow_semantic_ir.v1"`.
- `semantic_ir.workflows[bundle.surface.name]` exists and records statement ids in authored step order.
- the executable bridge references every node id in `bundle.ir.nodes` and every projection presentation key used by `bundle.runtime_plan`.
- command effects preserve `external_tool` vs `certified_adapter` classification without inspecting command text.
- a deliberately corrupted bridge payload fails validation with `semantic_ir_invalid`.

Recommended test names:

- `test_derive_semantic_ir_from_yaml_bundle_records_contracts_refs_effects_and_bridges`
- `test_semantic_ir_helper_returns_shared_surface_from_loaded_bundle`
- `test_semantic_ir_validation_rejects_missing_executable_bridge_node`
- `test_load_returns_typed_bundle_with_semantic_ir`

- [ ] **Step 2: Run collection and the narrow shared-bundle selectors first**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_semantic_ir.py tests/test_workflow_ir_lowering.py tests/test_loader_validation.py -q
python -m pytest tests/test_workflow_semantic_ir.py tests/test_workflow_ir_lowering.py tests/test_loader_validation.py -k "semantic_ir or loaded_bundle" -q
```

Expected:

- collection succeeds once the new test module exists;
- the test run fails because `orchestrator/workflow/semantic_ir.py` and `LoadedWorkflowBundle.semantic_ir` do not exist yet.

- [ ] **Step 3: Implement `orchestrator/workflow/semantic_ir.py` as one shared schema/builder/validator module**

Implement:

- schema constant:

```python
WORKFLOW_SEMANTIC_IR_SCHEMA_VERSION = "workflow_semantic_ir.v1"
```

- public dataclasses:
  - `SemanticWorkflowIR`
  - `SemanticWorkflow`
- lightweight internal/public support dataclasses for:
  - statement bridges
  - contract entries
  - ref entries
  - effect entries
  - proof entries
  - state-layout entries
  - source-map bridge entries
- public functions:
  - `derive_workflow_semantic_ir(...)`
  - `validate_workflow_semantic_ir(...)`
  - `workflow_semantic_ir_to_json(...)` or equivalent serializer used by `_json_data(...)`

Builder inputs must be:

```python
derive_workflow_semantic_ir(
    surface=surface,
    ir=ir,
    projection=projection,
    runtime_plan=runtime_plan,
    imports=imports,
    provenance=surface.provenance,
)
```

Validation must reject:

- unresolved contract/ref/effect/proof/state-layout ids;
- executable bridge node ids missing from `ExecutableWorkflow.nodes`;
- presentation keys or checkpoint refs absent from `WorkflowStateProjection` / `WorkflowRuntimePlan`;
- compiled-frontend source-map bindings that reference missing origin keys or subject refs;
- command entries that claim `certified_adapter` without declared adapter/tool identity.

- [ ] **Step 4: Thread Semantic IR through the shared bundle**

Update `orchestrator/workflow/loaded_bundle.py`:

- add `semantic_ir: SemanticWorkflowIR` to `LoadedWorkflowBundle`;
- add `workflow_semantic_ir(workflow_or_bundle)` helper matching the existing runtime-plan helper style.

Update `orchestrator/workflow/lowering.py`:

- derive `semantic_ir` immediately after `runtime_plan`;
- keep `ExecutableWorkflow` and `WorkflowStateProjection` derivation unchanged;
- construct `LoadedWorkflowBundle` with:

```python
return LoadedWorkflowBundle(
    surface=surface,
    semantic_ir=semantic_ir,
    ir=ir,
    projection=projection,
    runtime_plan=runtime_plan,
    imports=MappingProxyType(dict(imports)),
    provenance=surface.provenance,
)
```

- [ ] **Step 5: Re-run the shared-contract selectors and make them pass**

Run:

```bash
python -m pytest tests/test_workflow_semantic_ir.py tests/test_workflow_ir_lowering.py tests/test_loader_validation.py -k "semantic_ir or loaded_bundle" -q
```

Expected: PASS, with YAML loader and shared lowering both returning bundles that carry deterministic Semantic IR.

## Task 2: Emit `semantic_ir.json` And Update Manifest/Coverage/Explain Surfaces

**Files:**

- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `orchestrator/workflow_lisp/source_map.py`
- Modify: `orchestrator/cli/commands/explain.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_cli.py`
- Modify: `tests/test_runtime_observability.py`

- [ ] **Step 1: Add failing artifact, coverage, and explain tests**

Extend the existing build/CLI/observability tests so they assert the new contract:

- `semantic_ir.json` is emitted and listed in `artifact_paths`.
- `manifest.artifact_status["semantic_ir"] == "emitted"`.
- `manifest.artifact_status["core_workflow_ast"] == "deferred_shared_contract"`.
- source-map coverage and runtime-observability coverage dictionaries now report `semantic_ir: covered`.
- `explain_workflow(...)` prints `Deferred artifacts: core_workflow_ast`.
- explain output includes a `Semantic IR:` section with the selected workflow name and schema version.

Update or add tests around these existing cases:

- `test_build_emits_required_artifacts_and_deferred_status_entries`
- `test_build_runtime_plan_artifact_matches_selected_workflow_lineage_and_manifest`
- `test_build_manifest_records_source_map_schema_and_coverage_for_emitted_artifacts`
- `test_source_map_emits_versioned_schema_and_runtime_lineage_sections`
- a new explain test such as `test_explain_workflow_prints_semantic_ir_and_only_core_ast_as_deferred`
- runtime observability provenance expectations in `tests/test_runtime_observability.py`

- [ ] **Step 2: Run the narrow build/explain selectors**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_cli.py tests/test_runtime_observability.py -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_cli.py tests/test_runtime_observability.py -k "semantic_ir or explain or source_map_coverage or compiled_frontend" -q
```

Expected: FAIL because `semantic_ir.json` is not written yet, the manifest still marks `semantic_ir` deferred, coverage is stale, and explain still advertises both artifacts as deferred.

- [ ] **Step 3: Emit the new artifact and update the manifest/coverage surfaces**

Update `orchestrator/workflow_lisp/build.py`:

- preserve `selected_bundle.semantic_ir` when reconstructing `validated_bundle`;
- add `"semantic_ir": build_root / "semantic_ir.json"` to `_write_build_artifacts(...)`;
- serialize `validated_bundle.semantic_ir`;
- include the new relpath in `FrontendBuildManifest.artifact_paths`;
- change `artifact_status` to:

```python
{
    "core_workflow_ast": "deferred_shared_contract",
    "semantic_ir": "emitted",
}
```

Update `orchestrator/workflow_lisp/source_map.py`:

- change only the `semantic_ir` coverage entry from `deferred_shared_contract` to `covered`;
- keep `core_workflow_ast` deferred.

Update any runtime-observability expectations that read `frontend_source_map_coverage` so they match the new coverage status and nothing else.

- [ ] **Step 4: Expose Semantic IR in `orchestrate explain`**

Update `orchestrator/cli/commands/explain.py`:

- reduce the banner to `Deferred artifacts: core_workflow_ast`;
- print a `Semantic IR:` section before or after `Executable nodes:` using the selected bundle's shared object, not a frontend-private reconstruction;
- serialize only the selected workflow slice plus any top-level schema/version fields needed for explain readability.

The explain section should let a reviewer verify:

- schema version;
- selected workflow name;
- statement ids;
- command boundary metadata;
- presence of bridge ids back to executable nodes and presentation keys.

- [ ] **Step 5: Re-run the artifact/explain selectors**

Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_cli.py tests/test_runtime_observability.py -k "semantic_ir or explain or source_map_coverage or compiled_frontend" -q
```

Expected: PASS, with emitted `semantic_ir.json`, updated coverage, and explain output that only leaves `core_workflow_ast` deferred.

## Task 3: Surface `semantic_ir_invalid` Deterministically

**Files:**

- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`
- Modify only if a failing test proves it is required: `orchestrator/workflow_lisp/compiler.py`
- Modify only if a failing test proves it is required: `orchestrator/workflow_lisp/validation.py`

- [ ] **Step 1: Add failing diagnostics tests for Semantic IR classification**

Extend `tests/test_workflow_lisp_diagnostics.py` to cover two things:

- metadata inference for `semantic_ir_invalid`:
  - `phase == "semantic_ir"`
  - `validation_pass == "semantic_ir"`
  - `authority_layer == "shared"`
- a deterministic failure path where the Semantic IR builder/validator raises a structured failure and the resulting diagnostic preserves the authored span/form-path metadata when available.

Recommended tests:

- `test_serialize_diagnostic_infers_semantic_ir_metadata_from_code`
- `test_semantic_ir_invalid_preserves_structured_subject_ref_bridge`

Use monkeypatching to force the new builder/validator to fail on a known lowered workflow instead of inventing a second fixture format.

- [ ] **Step 2: Run the narrow diagnostics selector**

Run:

```bash
python -m pytest tests/test_workflow_lisp_diagnostics.py -k "semantic_ir" -q
```

Expected: FAIL because diagnostics metadata does not yet know the `semantic_ir` pass and no failure classification path exists for the new shared builder.

- [ ] **Step 3: Implement the diagnostics classification and bridge**

Update `orchestrator/workflow_lisp/diagnostics.py`:

- add `"semantic_ir": "semantic_ir"` to `_VALIDATION_PASS_TO_PHASE` and `_PHASE_TO_VALIDATION_PASS`;
- insert `"semantic_ir"` in `_VALIDATION_PASS_ORDER` between `"shared_validation"` and `"executable"`;
- add code-path inference so `semantic_ir_invalid` resolves to validation pass `semantic_ir`;
- default `authority_layer` to `"shared"` for the `semantic_ir` pass rather than `"frontend"`.

If the focused failing test proves it necessary, add a narrow bridge in `compiler.py` / `validation.py` so semantic-IR builder failures are reported as their own pass result instead of being flattened into `shared_validation`. Do this only if the tests cannot be satisfied by shared diagnostic metadata and error conversion alone.

- [ ] **Step 4: Re-run the diagnostics selector**

Run:

```bash
python -m pytest tests/test_workflow_lisp_diagnostics.py -k "semantic_ir" -q
```

Expected: PASS, with `semantic_ir_invalid` classified as shared semantic-IR validation rather than generic parse/source-map/shared-validation fallout.

## Task 4: Full Verification And Smoke Checks

**Files:**

- No new ownership. This task is verification-only.

- [ ] **Step 1: Run the required targeted pytest checks**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_semantic_ir.py -q
python -m pytest tests/test_workflow_semantic_ir.py -q
python -m pytest tests/test_workflow_ir_lowering.py tests/test_loader_validation.py -k "semantic_ir or loaded_bundle" -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_cli.py -k "semantic_ir or explain or build_artifacts" -q
python -m pytest tests/test_workflow_lisp_diagnostics.py tests/test_runtime_observability.py -k "semantic_ir or source_map_coverage or compiled_frontend" -q
```

Expected: all PASS.

- [ ] **Step 2: Run real orchestrator smoke checks from the repo root**

Run:

```bash
python -m orchestrator compile tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix/neurips/entry.orc --entry-workflow orchestrate --source-root tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix --provider-externs-file tests/fixtures/workflow_lisp/cli/providers.json --prompt-externs-file tests/fixtures/workflow_lisp/cli/prompts.json --imported-workflow-bundles-file tests/fixtures/workflow_lisp/cli/imported_workflow_bundles.json --command-boundaries-file tests/fixtures/workflow_lisp/cli/commands.json
python -m orchestrator explain tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix/neurips/entry.orc --form orchestrate --entry-workflow orchestrate --source-root tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix --provider-externs-file tests/fixtures/workflow_lisp/cli/providers.json --prompt-externs-file tests/fixtures/workflow_lisp/cli/prompts.json --imported-workflow-bundles-file tests/fixtures/workflow_lisp/cli/imported_workflow_bundles.json --command-boundaries-file tests/fixtures/workflow_lisp/cli/commands.json
```

Expected:

- compile succeeds and writes `.orchestrate/build/<fingerprint>/semantic_ir.json`;
- the emitted `manifest.json` marks `semantic_ir` emitted and `core_workflow_ast` deferred;
- explain output contains `Deferred artifacts: core_workflow_ast`;
- explain output contains a `Semantic IR:` section for `neurips/entry::orchestrate`.

- [ ] **Step 3: Record the outcome in the implementation summary**

When implementation is complete, record:

- exact files changed;
- which pytest selectors were run and their observed PASS results;
- the compile/explain smoke-check commands that were run;
- confirmation that `core_workflow_ast` remains deferred while `semantic_ir` is implemented and emitted.

## Completion Criteria

The slice is complete only when all of the following are true:

- `orchestrator/workflow/semantic_ir.py` defines a real shared `SemanticWorkflowIR` contract, builder, validator, and serializer.
- `LoadedWorkflowBundle` carries `semantic_ir`, and helper accessors mirror the existing bundle helper style.
- YAML-loaded and Workflow Lisp-compiled bundles both expose deterministic Semantic IR derived from validated shared structures.
- compiled Workflow Lisp builds emit `semantic_ir.json` and mark it `emitted`.
- source-map/runtime-observability coverage reports `semantic_ir: covered` while leaving `core_workflow_ast` deferred.
- `orchestrate explain` no longer treats `semantic_ir` as deferred and can display the selected workflow's Semantic IR slice.
- Semantic IR validation failures surface as `semantic_ir_invalid` with shared-authority metadata and structured provenance when available.
