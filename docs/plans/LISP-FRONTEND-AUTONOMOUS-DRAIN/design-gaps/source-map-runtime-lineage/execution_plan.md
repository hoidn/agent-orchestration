# Workflow Lisp Source Map Runtime Lineage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the bounded Workflow Lisp source-map/runtime-lineage slice so authored `.orc` provenance survives lowering, shared validation, build artifacts, executable IR, and runtime observability without fabricating unavailable Core AST or Semantic IR artifacts.

**Architecture:** Keep `orchestrator/workflow_lisp/` as the frontend-owned provenance layer, reuse the existing lowered-authored-mapping -> shared validation -> executable IR seam, and promote `source_map.json` into the canonical persisted lineage sidecar. Replace message-text-only remapping with structured validation subject references, let runtime observability resolve compiled frontend origins by executable node first and surface step id second, and transport command-boundary provenance only through declared `external_tool`/`certified_adapter` metadata instead of inferred script behavior.

**Tech Stack:** Python dataclasses, `orchestrator/workflow_lisp`, `orchestrator/workflow`, `orchestrator/runtime_observability.py`, `orchestrator/exceptions.py`, pytest, and the existing Workflow Lisp CLI/build fixtures.

---

## Fixed Inputs

Read these before implementation and treat them as authority:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `0. Prerequisites, Boundaries, And Missing Internal Specs`
  - `45. Core Workflow AST`
  - `46. Validated Core Workflow AST`
  - `47. Semantic IR`
  - `48. Executable IR`
  - `59. Validation Sequence`
  - `72. Lowering Errors`
  - `74. Source Map Requirements`
  - `75. Runtime Observability`
  - `76. Build Artifacts`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `6. Lowering Contract`
  - `9. Source Spans And Diagnostics`
  - `10. Validation`
  - `14. Implementation Stages`
- `docs/design/workflow_lisp_source_map.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

## Current Repo Baseline

Assume this exact starting point:

- `docs/steering.md` is empty in this checkout and does not widen scope.
- `progress_ledger.json` is empty, so the checked-in design docs and visible test output are the only authoritative progress record.
- `orchestrator/workflow_lisp/lowering.py` already defines `LoweringOrigin` and `LoweringOriginMap`.
- `orchestrator/workflow_lisp/build.py` already emits:
  `frontend_ast.json`,
  `expanded_frontend_ast.json`,
  `typed_frontend_ast.json`,
  `lowered_workflows.json`,
  `executable_ir.json`,
  `source_map.json`,
  and `diagnostics.json`.
- `source_map.json` currently records only workflow origins, step ids, generated inputs, generated outputs, and generated paths.
- `orchestrator/workflow/surface_ast.py` already carries compiled-frontend provenance bridge fields.
- `orchestrator/runtime_observability.py` already persists `compiled_frontend` metadata into run state.
- `orchestrator/workflow/executor.py` already logs compiled frontend source context, but only from step-level origin lookups.
- `orchestrator/workflow_lisp/lowering.py` still remaps shared-validation failures by scanning error-message text for generated names.
- `FrontendBuildManifest.artifact_status` already marks `core_workflow_ast` and `semantic_ir` as deferred shared contracts. Preserve that honesty rule.

## Hard Scope Limits

Implement only the bounded source-map/runtime-lineage tranche described in the work-item context:

- stable origin keys for generated workflow surfaces;
- one dedicated `source_map.json` schema plus coverage validation;
- structured validation-subject references for deterministic remapping;
- executable-node lineage persisted from validated executable IR;
- runtime compiled-frontend provenance and source-trace loading;
- certified-adapter provenance transport across `command-result`, `external_tool`, and `certified_adapter` boundaries only through declared adapter metadata;
- focused build, diagnostics, lowering, and runtime verification.

Explicit non-goals:

- no new frontend language forms, macros, procedures, phase/resource/drain behavior, or workflow-ref design work;
- no redesign of Core AST, Semantic IR, TypeCatalog, pointer authority, or variant proof;
- no report parsing, no hidden script semantics, and no new command-adapter policy;
- no second executor path, no YAML-as-authority fallback, and no fabricated `core_workflow_ast` or `semantic_ir` artifacts.

## Non-Negotiable Implementation Rules

Do not re-decide any of these during execution:

- `source_map.json` remains the canonical persisted lineage sidecar under the frontend build root.
- The frontend keeps using the existing authored-mapping -> `elaborate_surface_workflow(...)` -> `lower_surface_workflow(...)` seam.
- Structured validation subject refs are the steady-state remap path; substring matching remains only as a compatibility fallback and must stay regression-tested.
- Executable-node lineage is first-class and must cover control-flow/finalization nodes that surface at runtime, not just authored step ids.
- Runtime observability must consume the persisted sidecar; it must not recompile `.orc` source during `run` or `resume`.
- Core AST and Semantic IR coverage remain explicitly deferred shared contracts until the shared codebase exposes those artifacts directly.
- Certified-adapter provenance stays declarative. Do not parse adapter reports or stdout to reconstruct lineage.

## File Ownership

Modify:

- `orchestrator/workflow_lisp/source_map.py` (new)
- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/exceptions.py`
- `orchestrator/runtime_observability.py`
- `orchestrator/workflow/elaboration.py`
- `orchestrator/workflow/executable_ir.py`
- `orchestrator/workflow/executor.py`
- `orchestrator/workflow/surface_ast.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_diagnostics.py`
- `tests/test_runtime_observability.py`
- `tests/test_runtime_observability_cli.py`

Modify only if a targeted failing test proves the passthrough is necessary:

- `orchestrator/loader.py`

Do not broaden ownership into reader/typechecker/module/stdlib code. This slice is provenance plumbing, not a language-surface expansion.

## Task 1: Lock The Persisted Source-Map Schema

**Files:**

- Create: `orchestrator/workflow_lisp/source_map.py`
- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] **Step 1: Add failing build-artifact tests for the new schema**

Extend `tests/test_workflow_lisp_build_artifacts.py` so `source_map.json` must expose:

- top-level `schema_version == "workflow_lisp_source_map.v1"`;
- top-level `coverage` with:
  `frontend_ast`,
  `lowered_surface`,
  `shared_validation_subjects`,
  `executable_ir`,
  `runtime_logs`,
  `core_workflow_ast`,
  `semantic_ir`;
- per-workflow lineage sections for:
  `workflow_origin`,
  `step_ids`,
  `generated_inputs`,
  `generated_outputs`,
  `generated_paths`,
  `generated_internal_inputs`,
  `command_boundaries`,
  `validation_subjects`,
  `executable_nodes`;
- selected-entry-workflow marking that still distinguishes canonical names with shared display names.

Keep the tests asserting that contract definitions are absent from the sidecar and that deferred shared contracts stay explicit rather than silently omitted.

- [ ] **Step 2: Run the narrow build-artifact selector and confirm it fails first**

Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k 'source_map or source_trace or emitted_artifacts' -q
```

Expected: FAIL because the current serializer does not emit `schema_version`, coverage metadata, command-boundary lineage, validation subjects, executable-node lineage, or generated internal inputs.

- [ ] **Step 3: Implement the dedicated source-map data model**

In `orchestrator/workflow_lisp/source_map.py`, define the normalized frontend-owned schema and keep serialization logic out of `build.py`. The module should expose typed helpers for:

- one authored origin entry carrying `origin_key`, `entity_kind`, `workflow_name`, path/span/form-path metadata, expansion stack, and notes;
- one command-boundary lineage entry carrying `step_id`, `command_name`, `boundary_kind`, `origin_key`, and optional declared adapter metadata such as `source_map_behavior`;
- one validation-subject binding carrying `ValidationSubjectRef` -> `origin_key`;
- one executable-node lineage record carrying `node_id`, `step_id`, `kind`, `region`, and `origin_key`;
- one top-level document object carrying `schema_version`, `coverage`, and `workflows`;
- one validator that rejects duplicate origin keys, missing subject bindings, unmapped executable nodes, and invalid coverage claims with deterministic frontend diagnostics.

Keep command-boundary, executable-node, and validation-subject data nested under each workflow entry instead of inventing a parallel global map.

- [ ] **Step 4: Replace the ad hoc serializer in `build.py`**

Refactor `_serialize_source_map(...)` and `_origin_payload(...)` into a call to the new module. Keep `build.py` responsible only for assembling compile/build inputs, command-boundary metadata, invoking the source-map builder, validating the finished document, and writing `source_map.json`.

- [ ] **Step 5: Re-run the selector and require a pass**

Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k 'source_map or source_trace or emitted_artifacts' -q
```

Expected: PASS with the new schema and no fake Core AST or Semantic IR payloads.

## Task 2: Thread Stable Origin Keys And Structured Validation Subjects

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `orchestrator/exceptions.py`
- Modify: `orchestrator/workflow/elaboration.py`
- Modify if required: `orchestrator/loader.py`
- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`

- [ ] **Step 1: Add failing lowering and diagnostics tests**

Add or update tests so they fail first for these contracts:

- every lowered workflow root, step id, `command-result` boundary, flattened boundary input/output, generated path, and generated internal input has a stable origin key;
- shared-validation remapping prefers structured subject refs over message substring matching;
- legacy message-only errors still fall back to the old name-scan path while the transition remains in place;
- missing subject bindings raise a deterministic source-map diagnostic instead of silently falling back to the workflow root.

- [ ] **Step 2: Add a generic validation-subject carrier**

In `orchestrator/exceptions.py`, introduce a shared generic carrier:

```text
ValidationSubjectRef(subject_kind, subject_name, workflow_name?)
```

Extend `ValidationError` to carry zero or more subject refs without making shared validation depend on Workflow Lisp-specific types or diagnostics.

- [ ] **Step 3: Attach subject refs at the shared-validation seam**

Update the elaboration/validation bridge so step-, workflow-, input-, output-, and path-related validation errors can attach the generated subject they already know about. Keep shared validation generic:

- `orchestrator/workflow/elaboration.py` should accept and forward optional subject refs when surfacing validation failures;
- if the existing backend interface forces the loader to change, keep the `orchestrator/loader.py` edit signature-only and backward-compatible for callers that still pass just a message.

- [ ] **Step 4: Enrich lowering provenance with deterministic keys and bindings**

In `orchestrator/workflow_lisp/lowering.py`:

- extend `LoweringOrigin` with a stable `origin_key`;
- keep `LoweringOriginMap` authoritative for lowering-time provenance, but add explicit collections for:
  `generated_internal_inputs`,
  `validation_subject_bindings`,
  and any workflow-name metadata needed by the source-map builder;
- make origin keys deterministic from canonical workflow name plus generated entity kind/name, not timestamps or enumeration order that can drift across equivalent recompiles;
- teach `_raise_remapped_validation_error(...)` to resolve `ValidationSubjectRef` bindings first and call `_remap_validation_message(...)` only when no structured ref is available.

Preserve existing notes/expansion-stack data so remapped diagnostics still explain macro/procedure provenance.

- [ ] **Step 5: Re-run the focused selectors**

Run:

```bash
python -m pytest tests/test_workflow_lisp_lowering.py -k 'origin_map or provenance or source_map' -q
python -m pytest tests/test_workflow_lisp_diagnostics.py -k 'source_map or shared_validation or provenance' -q
```

Expected: PASS with structured remapping active and the fallback path still covered.

## Task 3: Persist Coverage, Provenance, And Command-Boundary Metadata Through The Build And Runtime Bridge

**Files:**

- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow/surface_ast.py`
- Modify: `orchestrator/runtime_observability.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_runtime_observability.py`
- Modify: `tests/test_runtime_observability_cli.py`

- [ ] **Step 1: Add failing tests for compiled-frontend metadata**

Extend the build/runtime tests so they require:

- manifest-visible source-map schema/version and coverage metadata;
- `source_map.json` command-boundary lineage entries where `external_tool` steps inherit the authored `command-result` origin and `certified_adapter` steps preserve declared `source_map_behavior` without inventing new semantics;
- persisted runtime `compiled_frontend` state that records the build root, source-map path, schema version, and coverage summary for `.orc` runs;
- selected entry workflow names remaining canonical in runtime metadata.

- [ ] **Step 2: Transport declared command-boundary metadata into the source-map bridge**

In `orchestrator/workflow_lisp/build.py`, join lowered `command-result` provenance with the command-boundary environment that the build already parses:

- record one command-boundary lineage entry per lowered boundary under the owning workflow entry;
- for `external_tool`, inherit the authored `command-result` origin and boundary identity only;
- for `certified_adapter`, copy only declared manifest metadata needed for provenance transport, especially `source_map_behavior`;
- never parse adapter reports, inspect stdout, or synthesize undeclared adapter semantics.

- [ ] **Step 3: Carry schema metadata on workflow provenance**

In `orchestrator/workflow/surface_ast.py`, add optional frontend provenance fields for source-map schema/version and coverage summary. Keep them opaque runtime metadata, not new semantic authority.

In `orchestrator/workflow_lisp/build.py`, populate those fields when replacing bundle provenance for the selected validated bundle.

- [ ] **Step 4: Keep build-manifest claims honest**

Update the frontend build manifest so it records the source-map schema/version and coverage summary while preserving:

- `core_workflow_ast: deferred_shared_contract`
- `semantic_ir: deferred_shared_contract`

Do not claim those surfaces are covered just because the source-map document now reserves slots for them.

- [ ] **Step 5: Persist the richer bridge data into runtime state**

Update `record_compiled_frontend_provenance(...)` in `orchestrator/runtime_observability.py` so the persisted payload includes the new schema/version and coverage data alongside the existing build-root and source-trace-path fields.

Keep the runtime-side source-map loader/executor helpers able to expose command-boundary lineage metadata to source-context formatting without turning that metadata into new semantic authority or execution branching.

Only change `orchestrator/workflow_lisp/compiler.py` if the builder genuinely needs an additional structured view from `LinkedStage3CompileResult`; prefer preserving the current compiler API if the build layer can derive everything it needs already.

- [ ] **Step 6: Re-run the build/runtime provenance selectors**

Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k 'source_map or source_trace or emitted_artifacts' -q
python -m pytest tests/test_runtime_observability.py tests/test_runtime_observability_cli.py -k 'compiled_frontend or source_context' -q
```

Expected: PASS with runtime state carrying schema-aware compiled-frontend metadata and tests covering both inherited `external_tool` provenance and declared `certified_adapter` transport.

## Task 4: Emit And Consume Executable-Node Lineage

**Files:**

- Modify: `orchestrator/workflow/executable_ir.py`
- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_runtime_observability.py`
- Modify: `tests/test_runtime_observability_cli.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] **Step 1: Add failing runtime-observability tests for node-first lookup**

Add tests that fail first for these behaviors:

- runtime source lookup checks executable `node_id` lineage before falling back to surface `step_id`;
- control-flow or finalization nodes can still explain their authored origin when they appear in logs;
- command-boundary nodes or steps surface declared adapter metadata from the persisted sidecar when present, while plain `external_tool` entries remain authored-origin lookups without invented adapter fields;
- step-only lineage remains a compatibility fallback for older source-map payloads.

- [ ] **Step 2: Expose executable-node metadata without redesigning the IR**

Use the existing `ExecutableWorkflow.nodes` / `ExecutableNodeBase` fields as the source of truth. Only add a small helper in `orchestrator/workflow/executable_ir.py` if needed to serialize a stable projection of:

- `node_id`
- `step_id`
- `kind`
- `region`
- `presentation_name`

Do not redesign executable-node dataclasses for this tranche unless the tests prove the current fields are insufficient.

- [ ] **Step 3: Emit executable-node lineage into `source_map.json`**

In the build layer, join validated executable IR nodes back to lowering origins by stable origin key and persist them under each workflow entry. Require one lineage record for every runtime-observable node in the validated bundle, including finalization/control-flow nodes that may not correspond one-to-one with authored steps.

- [ ] **Step 4: Teach the executor to use node lineage first**

Refactor the compiled-frontend lookup helpers in `orchestrator/workflow/executor.py` so the executor:

- loads the persisted source-map sidecar once;
- indexes executable-node lineage and step-id lineage separately;
- keeps command-boundary lineage metadata indexed alongside those lookups so source-context formatting can mention adapter identity and `source_map_behavior` when the persisted sidecar provides them;
- resolves runtime provenance by `node_id` first, then `step_id`, then the existing compatibility candidates;
- continues logging the generated runtime step name while also logging authored `source:` and `form:` lines when a lineage match is available.

- [ ] **Step 5: Re-run the runtime selectors**

Run:

```bash
python -m pytest tests/test_runtime_observability.py tests/test_runtime_observability_cli.py -k 'compiled_frontend or source_context' -q
```

Expected: PASS with runtime logs explainable for executable nodes beyond plain authored steps.

## Task 5: Final Verification And Compile Smoke

**Files:**

- Modify only as needed to fix failing tests from Tasks 1-4.

- [ ] **Step 1: Run collection on every touched test module**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_diagnostics.py tests/test_runtime_observability.py tests/test_runtime_observability_cli.py -q
```

Expected: collection succeeds and includes the new source-map/runtime-lineage tests.

- [ ] **Step 2: Re-run the focused verification suite from the recorded check bundle**

Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k 'source_map or source_trace or emitted_artifacts' -q
python -m pytest tests/test_workflow_lisp_lowering.py -k 'origin_map or provenance or source_map' -q
python -m pytest tests/test_workflow_lisp_diagnostics.py -k 'source_map or shared_validation or provenance' -q
python -m pytest tests/test_runtime_observability.py tests/test_runtime_observability_cli.py -k 'compiled_frontend or source_context' -q
```

Expected: all selectors pass without weakening assertions or removing fallback coverage.

- [ ] **Step 3: Run the frontend compile smoke command**

Run:

```bash
python -m orchestrator compile tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix/neurips/entry.orc --entry-workflow orchestrate --source-root tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix --provider-externs-file tests/fixtures/workflow_lisp/cli/providers.json --prompt-externs-file tests/fixtures/workflow_lisp/cli/prompts.json --imported-workflow-bundles-file tests/fixtures/workflow_lisp/cli/imported_workflow_bundles.json --command-boundaries-file tests/fixtures/workflow_lisp/cli/commands.json
```

Expected: exit code `0`, a fresh build root under `.orchestrate/build/`, and an emitted `source_map.json` whose selected workflow is `neurips/entry::orchestrate`.

The smoke command only exercises the `external_tool` command-boundary path from `tests/fixtures/workflow_lisp/cli/commands.json`; rely on the focused pytest selectors above to cover `certified_adapter` transport with inline or dedicated test fixtures.

- [ ] **Step 4: Record the implementation evidence**

Before closing the work, capture:

- which source-map schema fields were added;
- which command-boundary lineage fields now distinguish inherited `external_tool` provenance from declared `certified_adapter` metadata;
- where structured validation subject refs are now attached;
- how runtime lookup order changed;
- which pytest selectors and compile smoke command passed.

Do not claim completion from inspection alone.
