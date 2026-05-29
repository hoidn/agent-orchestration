# Workflow Lisp Frontend Validation And Diagnostics Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement one deterministic Workflow Lisp validation and diagnostics pipeline that classifies frontend-local and shared-validation failures from parse through executable/runtime-facing checks without inventing fake Core AST or Semantic IR validation surfaces.

**Architecture:** Keep `orchestrator/workflow_lisp/` as the frontend-owned validation layer, add one explicit `validation.py` orchestrator over the existing staged compile path, and preserve the current lowering -> shared validation -> executable/runtime seam. Extend `LispFrontendDiagnostic` and `diagnostics.json` with exact `validation_pass` and `authority_layer` metadata, enforce `.orc` authority-preflight rules before shared validation, and preserve shared codes while remapping their provenance through structured subject refs first and message fallback second.

**Tech Stack:** Python dataclasses, `orchestrator/workflow_lisp`, `orchestrator/workflow`, `orchestrator/exceptions.py`, pytest, existing Workflow Lisp fixtures under `tests/fixtures/workflow_lisp/`, and existing build/source-map/runtime-observability artifacts.

---

## Fixed Inputs

Read these before implementation and treat them as authority:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `59. Validation Sequence`
  - `60. Type Validation`
  - `61. Effect Validation`
  - `62. Contract Validation`
  - `63. Variant Proof Validation`
  - `64. Snapshot Validation`
  - `65. Pointer Authority Validation`
  - `66. Report-Authority Validation`
  - `67. Frontend Parse/Module Errors`
  - `68. Macro Errors`
  - `69. Type Errors`
  - `70. Effect Errors`
  - `71. Authority Errors`
  - `72. Lowering Errors`
  - `73. Existing v2.14 Errors Reused`
  - `74. Source Map Requirements`
  - `76.1 Editor And Lint Tooling Compatibility`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `9. Source Spans And Diagnostics`
  - `10. Validation`
  - `14. Implementation Stages`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-validation-diagnostics-pipeline/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/3/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

## Current Repo Baseline

Assume this exact starting point:

- `docs/steering.md` is empty in this checkout and does not widen scope.
- `progress_ledger.json` has no recorded events.
- `orchestrator/workflow_lisp/validation.py` does not exist yet.
- `orchestrator/workflow_lisp/compiler.py` currently coordinates the staged compile path directly and raises `LispFrontendCompileError` from feature-local checkpoints.
- `orchestrator/workflow_lisp/diagnostics.py` already defines `LispFrontendDiagnostic` and serializes `phase`, but it does not yet persist `validation_pass` or `authority_layer`.
- `orchestrator/workflow_lisp/lowering.py` already remaps shared-validation failures through `LoweringOriginMap` and structured `ValidationSubjectRef` support, with message-text fallback still present.
- `orchestrator/workflow_lisp/source_map.py` and `build.py` already emit `source_map.json` and build-manifest coverage metadata.
- Existing focused suites already cover the relevant fronts:
  - `tests/test_workflow_lisp_diagnostics.py`
  - `tests/test_workflow_lisp_lowering.py`
  - `tests/test_workflow_lisp_structured_results.py`
  - `tests/test_workflow_lisp_phase_stdlib.py`
  - `tests/test_workflow_lisp_resource_stdlib.py`
  - `tests/test_loader_validation.py`
  - `tests/test_workflow_lisp_build_artifacts.py`
  - `tests/test_runtime_observability.py`

Execution rule for this plan: if current code disagrees with the approved architecture above, the architecture and the tests written from this plan win.

## Hard Scope Limits

Implement only the bounded validation/diagnostics slice described in the work-item context:

- one frontend-owned pass catalog and ordered pipeline;
- exact ownership boundaries between frontend-local checks and shared validation;
- deterministic diagnostic metadata:
  `code`,
  `phase`,
  `validation_pass`,
  `authority_layer`,
  `span`,
  `form_path`,
  and remap notes;
- authority-preflight rules for report parsing, pointer-as-authority, inline semantic command glue, and uncertified semantic command boundaries;
- source-map and executable-lineage validation checkpoints before and after the shared-validation bridge;
- preserved shared codes with subject-ref-first provenance remapping;
- focused verification only for diagnostics, lowering, build artifacts, loader validation, and runtime observability.

Explicit non-goals:

- no new frontend language forms or behavior changes to macros, procedures, workflow refs, phase/resource/drain stdlib, or runtime execution;
- no redesign of shared Core AST, Semantic IR, TypeCatalog, SourceMap schema, pointer authority, variant proof, queue semantics, or persisted state layout;
- no new command-adapter certification policy, no new legacy-adapter policy, and no runtime-native effect promotion;
- no second validator, no YAML-as-authority fallback, and no fabricated `core_ast_invalid` or `semantic_ir_invalid` surfaces.

## Non-Negotiable Rules

Do not re-decide any of these during execution:

- `validation.py` is an orchestrator over existing validators, not a replacement for feature-local rule ownership.
- `LispFrontendDiagnostic` remains the only user-visible diagnostic channel.
- `phase` stays as the coarse CLI/build grouping; `validation_pass` is the exact filtering key.
- `authority_layer` has exactly two values in this tranche:
  `frontend`
  and `shared_validation`.
- Shared validation errors preserve their original stable shared code. Do not wrap or alias them into frontend-only codes.
- Structured subject refs are the preferred remap path for shared-validation failures; message-text matching stays only as a compatibility fallback and must attach an explicit note.
- Pointer files remain representations, not semantic authority.
- Reports remain views, not semantic state.
- Shared validation stays authoritative for lowered snapshot semantics, pointer publication/path legality, imported-bundle compatibility, and executable/runtime bundle legality.
- Build artifacts must continue to state that Core AST and Semantic IR coverage are deferred shared contracts.

## Required Validation Catalog

Implement and preserve this pass ordering:

1. `parse`
2. `module`
3. `macro`
4. `type`
5. `effect`
6. `reference`
7. `contract`
8. `proof`
9. `authority`
10. `lowering_surface`
11. `source_map`
12. `shared_validation`
13. `executable`

Deterministic phase mapping:

- `parse` -> `read`
- `module` -> `syntax`
- `macro` -> `macro`
- `type`, `effect`, `reference`, `contract`, `proof` -> `typecheck`
- `authority`, `lowering_surface` -> `lowering`
- `source_map` -> `source_map`
- `shared_validation` -> `shared_validation`
- `executable` -> `executable`

## File Ownership

Create:

- `orchestrator/workflow_lisp/validation.py`

Modify:

- `orchestrator/workflow_lisp/__init__.py`
- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/lowering.py`
- `tests/test_loader_validation.py`
- `tests/test_runtime_observability.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_diagnostics.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_resource_stdlib.py`
- `tests/test_workflow_lisp_structured_results.py`

Modify only if a targeted failing test proves the passthrough is necessary:

- `orchestrator/workflow_lisp/contracts.py`
- `orchestrator/workflow_lisp/procedures.py`
- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/loader.py`

Do not broaden ownership into reader/module/macro/parser grammar code unless a failing test shows those modules cannot report through the pipeline without a narrow metadata patch.

## Task 1: Lock The Diagnostic Metadata Contract

**Files:**

- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`

- [ ] **Step 1: Add failing serialization tests for the new metadata**

Extend `tests/test_workflow_lisp_diagnostics.py` so serialized diagnostics must include:

- `validation_pass`;
- `authority_layer`;
- preserved `phase`;
- unchanged `code`, `path`, `line`, `column`, `form_path`, and notes.

Cover both direct construction and inferred defaults:

- a frontend-local diagnostic such as `command_adapter_missing_contract`;
- a source-map diagnostic such as `source_map_validation_ref_missing`;
- a preserved shared-validation code such as `workflow_call_version_mismatch` or `pointer_authority_conflict`.

- [ ] **Step 2: Run collection on the touched test module**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_diagnostics.py -q
```

Expected: collection succeeds and the new metadata tests are listed.

- [ ] **Step 3: Run the narrow selector and confirm it fails first**

Run:

```bash
python -m pytest tests/test_workflow_lisp_diagnostics.py -k "serialize_diagnostic or validation_pass or authority_layer" -q
```

Expected: FAIL because `serialize_diagnostic(...)` does not yet emit `validation_pass` or `authority_layer`.

- [ ] **Step 4: Extend the frontend diagnostic model**

In `orchestrator/workflow_lisp/diagnostics.py`:

- add `validation_pass` and `authority_layer` to `LispFrontendDiagnostic`;
- add deterministic inference helpers so existing call sites keep working while pipeline wiring lands;
- preserve the current renderer contract and location formatting;
- keep shared codes unchanged while classifying them under the exact pass/authority mapping from the approved architecture.

- [ ] **Step 5: Re-run the selector and require a pass**

Run:

```bash
python -m pytest tests/test_workflow_lisp_diagnostics.py -k "serialize_diagnostic or validation_pass or authority_layer" -q
```

Expected: PASS with the new serialized metadata present.

## Task 2: Add The Validation Pipeline Orchestrator

**Files:**

- Create: `orchestrator/workflow_lisp/validation.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/__init__.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`

- [ ] **Step 1: Add failing tests for pass ordering and blocking**

Add focused tests that prove:

- frontend diagnostics produced during compile carry the expected `validation_pass`;
- later passes do not run when an earlier blocking pass fails;
- shared validation is not invoked when blocking diagnostics already exist upstream.

Prefer `tmp_path` inputs and lightweight monkeypatching around the compiler seam over new permanent fixtures.

- [ ] **Step 2: Run the focused selector and confirm it fails**

Run:

```bash
python -m pytest tests/test_workflow_lisp_diagnostics.py -k "blocking or validation pipeline or shared validation" -q
```

Expected: FAIL because there is no dedicated pipeline module or pass-order enforcement yet.

- [ ] **Step 3: Introduce `validation.py` as the single orchestration layer**

Implement in `orchestrator/workflow_lisp/validation.py`:

- one pass-id enum or equivalent stable constants for the 13-pass catalog;
- one aggregate pipeline-state dataclass covering optional staged artifacts;
- one pass-result dataclass with:
  `pass_id`,
  `authority_layer`,
  `blocking`,
  `diagnostics`,
  and `artifact_ready`;
- one `run_validation_pipeline(...)` entrypoint that invokes existing stage contributors in the approved order and short-circuits later passes when required artifacts are missing.

- [ ] **Step 4: Refactor `compiler.py` to call the pipeline instead of open-coded raises**

Keep the current public entrypoints:

- `compile_stage1_module(...)`
- `compile_stage1_entrypoint(...)`
- `compile_stage3_module(...)`
- `compile_stage3_entrypoint(...)`

Refactor them so they:

- assemble staged frontend artifacts;
- hand those artifacts to `run_validation_pipeline(...)`;
- raise one aggregated `LispFrontendCompileError` only after the ordered pass results are known;
- keep feature-local validators as the rule authorities instead of duplicating their logic in the compiler.

- [ ] **Step 5: Re-run the selector and require a pass**

Run:

```bash
python -m pytest tests/test_workflow_lisp_diagnostics.py -k "blocking or validation pipeline or shared validation" -q
```

Expected: PASS with deterministic pass ordering and shared-validation gating.

## Task 3: Reclassify Existing Frontend Failures And Add The Authority Pass

**Files:**

- Modify: `orchestrator/workflow_lisp/validation.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify only if required: `orchestrator/workflow_lisp/contracts.py`
- Modify only if required: `orchestrator/workflow_lisp/workflows.py`
- Modify only if required: `orchestrator/workflow_lisp/procedures.py`
- Modify: `tests/test_workflow_lisp_structured_results.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_resource_stdlib.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`

- [ ] **Step 1: Add failing tests for authority-preflight behavior**

Cover these exact contracts with failing tests first:

- `.orc` `command-result` rejects `python -c`, `python -`, `bash -c`, `sh -c`, and single-string shell wrappers as `inline_python_command_in_workflow` or `inline_shell_command_in_workflow`;
- semantic command boundaries without certified-adapter metadata fail as `command_adapter_missing_contract` or the specific stdlib uncertified diagnostic;
- pointer-as-authority misuse in `resume-or-start` remains a hard frontend failure;
- resource-transition and reusable-state adapters keep failing at the frontend boundary when uncertified.

- [ ] **Step 2: Run collection on the touched suites**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_resource_stdlib.py tests/test_workflow_lisp_diagnostics.py -q
```

Expected: collection succeeds and the new authority-focused tests appear.

- [ ] **Step 3: Run the authority-focused selector and confirm it fails**

Run:

```bash
python -m pytest tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_resource_stdlib.py -k "command_adapter_missing_contract or inline_python or inline_shell or pointer_authority or uncertified" -q
```

Expected: FAIL because the current compile path classifies these through older stage-specific logic rather than one explicit `authority` pass.

- [ ] **Step 4: Implement the dedicated `authority` pass**

In `validation.py` and the narrowest necessary supporting modules:

- classify report-authority, pointer-authority, inline semantic command glue, and uncertified semantic command boundaries under `validation_pass = authority`;
- keep the current stable diagnostic codes wherever the meaning already matches;
- treat the command-adapter-contract lint names as hard errors for new `.orc` workflows;
- reuse existing stdlib metadata rather than reparsing reports, shell text, or pointer sidecars for meaning.

- [ ] **Step 5: Re-run the selector and require a pass**

Run:

```bash
python -m pytest tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_resource_stdlib.py -k "command_adapter_missing_contract or inline_python or inline_shell or pointer_authority or uncertified" -q
```

Expected: PASS with the exact same failure codes now classified under the `authority` pass.

## Task 4: Gate Lowering And Preserve Shared Validation Through The Bridge

**Files:**

- Modify: `orchestrator/workflow_lisp/validation.py`
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`

- [ ] **Step 1: Add failing tests for subject-ref-first remapping and shared-code preservation**

Extend the lowering and diagnostics coverage so it fails first for these contracts:

- shared-validation remapping prefers structured `ValidationSubjectRef` bindings over message substring matching;
- fallback-to-message remapping still works when subject refs are absent, but adds an explicit compatibility note;
- shared validation keeps its original code and only gains the new pass/authority metadata;
- missing validation-subject coverage yields a deterministic source-map diagnostic instead of silently blaming the workflow root.

- [ ] **Step 2: Run the focused selectors and confirm they fail**

Run:

```bash
python -m pytest tests/test_workflow_lisp_lowering.py -k "shared_validation or structured_validation_subject or source_map" -q
python -m pytest tests/test_loader_validation.py -k "pointer_authority_conflict or workflow_call_version_mismatch" -q
```

Expected: FAIL because the current bridge does not yet classify all remapped errors through the explicit pass catalog and fallback-note contract.

- [ ] **Step 3: Wire the lowering, source-map, and shared-validation passes**

Implement the pipeline seam so:

- `lowering_surface` verifies generated-id stability and lowering feasibility before shared validation;
- `source_map` confirms every generated validation subject and runtime-visible lowered surface is mapped before shared-validation remap relies on it;
- `shared_validation` calls the existing lowering/elaboration path only when upstream blocking diagnostics are clear;
- remapped shared diagnostics preserve shared codes exactly and receive `authority_layer = shared_validation`.

- [ ] **Step 4: Re-run the focused selectors and require a pass**

Run:

```bash
python -m pytest tests/test_workflow_lisp_lowering.py -k "shared_validation or structured_validation_subject or source_map" -q
python -m pytest tests/test_loader_validation.py -k "pointer_authority_conflict or workflow_call_version_mismatch" -q
```

Expected: PASS with preserved shared codes, correct pass classification, and explicit fallback notes only where structured refs are missing.

## Task 5: Add Executable-Pass Coverage And Persist The Metadata Through Build Artifacts

**Files:**

- Modify: `orchestrator/workflow_lisp/validation.py`
- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_runtime_observability.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`

- [ ] **Step 1: Add failing build-artifact and runtime-observability tests**

Cover these exact outputs:

- serialized diagnostics include `validation_pass` and `authority_layer` wherever `diagnostics.json` or direct diagnostic payloads are asserted;
- build-manifest and source-map coverage remain honest about deferred shared contracts;
- runtime-observability lineage continues to resolve compiled frontend provenance after executable-pass classification is added.

- [ ] **Step 2: Run collection on the touched modules**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_build_artifacts.py tests/test_runtime_observability.py tests/test_workflow_lisp_diagnostics.py -q
```

Expected: collection succeeds and the new executable/build metadata tests appear.

- [ ] **Step 3: Run the focused selector and confirm it fails**

Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py tests/test_runtime_observability.py -k "source_map or compiled_frontend or executable or diagnostics" -q
```

Expected: FAIL because the build/runtime artifact path does not yet persist the full validation metadata contract.

- [ ] **Step 4: Finish build and executable-pass integration**

In the narrowest necessary modules:

- classify executable/runtime-lineage validation under `validation_pass = executable`;
- keep `build.py` as a serializer/manifest layer rather than a second validator;
- ensure `diagnostics.json` serialization emits the new metadata without changing the source-map schema or the deferred-shared-contract honesty rule;
- preserve runtime-observability provenance behavior and ensure executable-node lineage remains covered.

- [ ] **Step 5: Re-run the selector and require a pass**

Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py tests/test_runtime_observability.py -k "source_map or compiled_frontend or executable or diagnostics" -q
```

Expected: PASS with persisted diagnostic metadata and unchanged source-map honesty.

## Task 6: Run The End-To-End Verification Set

**Files:**

- No new files

- [ ] **Step 1: Re-run collect-only for every touched suite**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_diagnostics.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_resource_stdlib.py tests/test_loader_validation.py tests/test_workflow_lisp_build_artifacts.py tests/test_runtime_observability.py -q
```

Expected: PASS with all added tests collected.

- [ ] **Step 2: Run the narrow verification commands from the approved architecture**

Run:

```bash
python -m pytest tests/test_workflow_lisp_diagnostics.py -k "shared_validation or source_map or command_adapter_missing_contract" -q
python -m pytest tests/test_workflow_lisp_lowering.py -k "shared_validation or structured_validation_subject or source_map" -q
python -m pytest tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_resource_stdlib.py -k "command_adapter_missing_contract or pointer_authority or uncertified" -q
python -m pytest tests/test_loader_validation.py -k "pointer_authority_conflict or workflow_call_version_mismatch" -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py tests/test_runtime_observability.py -k "source_map or compiled_frontend or executable" -q
```

Expected: PASS across all focused selectors.

- [ ] **Step 3: Run the broad slice regression suite**

Run:

```bash
python -m pytest tests/test_workflow_lisp_diagnostics.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_resource_stdlib.py tests/test_loader_validation.py tests/test_workflow_lisp_build_artifacts.py tests/test_runtime_observability.py -q
```

Expected: PASS with no regressions in the bounded validation/diagnostics slice.

- [ ] **Step 4: Record the verification evidence in the implementation handoff**

Capture in the final implementation summary:

- which files changed;
- which selectors failed first and then passed;
- which shared codes were preserved;
- whether any optional files such as `contracts.py`, `workflows.py`, `procedures.py`, or `loader.py` had to be touched and why.

## Acceptance Conditions

This slice is complete when:

- one deterministic validation pipeline governs Workflow Lisp compilation from parse through executable/runtime-facing checks;
- every diagnostic emitted by the frontend has:
  `code`,
  `span`,
  `form_path`,
  `phase`,
  `validation_pass`,
  and `authority_layer`;
- frontend-local and shared-validation ownership is explicit for every full-design validation category in scope;
- shared validation errors preserve their original stable shared code and remap to authored `.orc` provenance through structured subject refs when available;
- `.orc` workflows reject report parsing, pointer-as-authority, inline semantic command glue, and uncertified semantic command boundaries before shared validation;
- the implementation does not fabricate `core_ast_invalid` or `semantic_ir_invalid`.
