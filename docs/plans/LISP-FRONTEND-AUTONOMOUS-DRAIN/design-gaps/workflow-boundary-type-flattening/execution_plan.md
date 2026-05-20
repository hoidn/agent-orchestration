# Workflow Boundary Type Flattening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the bounded Workflow Lisp workflow-boundary projection contract so authored workflow signatures stay structured inside the frontend, flattening is limited to the current shared-surface compatibility seam, every projected field is source-mapped, and builds emit a deterministic `workflow_boundary_projection.json` artifact.

**Architecture:** Keep semantic authority in `WorkflowSignature`, typed workflow bodies, and existing frontend-owned provenance structures. Reuse `orchestrator/workflow_lisp/contracts.py` as the single authority for workflow-boundary projection metadata, thread that metadata through `lowering.py` and `compiler.py`, and emit the new artifact from compiler-owned metadata rather than re-deriving it from lowered mappings or overloading `source_map.json`.

**Tech Stack:** Python 3, dataclasses, `orchestrator.workflow_lisp`, shared workflow elaboration/lowering and loaded bundles, pytest, `.orc` fixtures already under `tests/fixtures/workflow_lisp/`, and `python -m orchestrator compile`.

---

## Fixed Inputs

Treat these as implementation authority for this slice:

- `docs/index.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `45. Core Workflow AST`
  - `47. Semantic IR`
  - `50. defworkflow Lowering`
  - `74. Source Map Requirements`
  - `76. Build Artifacts`
  - `77. Compile`
  - `110. Type Flattening`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `6. Lowering Contract`
  - `7. Provider And Command Results`
  - `9. Source Spans And Diagnostics`
  - `10. Validation`
  - `14. Implementation Stages`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/steering.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-boundary-type-flattening/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/9/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/9/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/9/selector/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

Current checkout facts that must not be rediscovered during execution:

- `docs/steering.md` is empty in this checkout and does not widen scope.
- `progress_ledger.json` has no events; do not infer partial completion from the ledger.
- The frontend package already exists under `orchestrator/workflow_lisp/`.
- `contracts.py` already defines `FlattenedContractField`, `derive_workflow_signature_contracts(...)`, and `UnionWorkflowBoundaryProjection`.
- `lowering.py` already records generated input/output/path provenance through `LoweringOriginMap`.
- `build.py` already emits `source_map.json` and other build artifacts, but not a dedicated workflow-boundary projection artifact.

## Hard Scope Limits

Implement only this bounded slice:

- preserve authored workflow params and returns as structured frontend authority;
- formalize recursive record flattening and union workflow-return projection as one compiler-owned boundary-projection contract;
- separate authored flattened boundary fields from compiler-generated internal write-root inputs;
- preserve provenance and source-trace coverage for every flattened field that can appear in shared-validation or build surfaces;
- emit deterministic `workflow_boundary_projection.json` build output and register it in the build manifest;
- add focused contract, lowering, workflow, and build-artifact verification only.

Explicit non-goals:

- no new frontend language forms, stdlib forms, macros, or runtime-native effects;
- no runtime execution changes or shared validation redesign;
- no redesign of Core Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant proof;
- no new command-boundary semantics, adapter framework changes, report parsing, pointer-as-state, or YAML-text generation;
- no widening of ownership into `orchestrator/workflow/` unless a targeted failing test proves the current frontend-owned seam cannot express the approved contract.

## File Ownership

Modify:

- `orchestrator/workflow_lisp/contracts.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/build.py`
- `tests/test_workflow_lisp_structured_results.py`
- `tests/test_workflow_lisp_workflows.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_build_artifacts.py`

Modify only if a targeted failing test proves the need:

- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/__init__.py`

Do not plan new checked-in fixtures by default. Prefer `tmp_path` inline modules in tests for collision, provenance-gap, and artifact-shape coverage unless an existing fixture becomes unreadable.

## Required Contracts

Keep these implementation contracts fixed during execution:

- `WorkflowSignature` remains the canonical structured workflow-boundary authority inside the frontend.
- Flattening is allowed only at:
  - lowered shared workflow `inputs`;
  - lowered shared workflow `outputs`;
  - lowered `call.with` bindings and `ref` targets;
  - build/explain artifacts that expose the projection mapping.
- `Provider`, `Prompt`, and `Json` remain non-boundary authored types except for existing compiler-known extern paths that never become ordinary workflow `inputs`.
- Managed write-root inputs remain generated lowering inputs and must not be reported as authored boundary params.
- `source_map.json` stays provenance-focused; the full contract mapping belongs in a separate artifact.

Add and preserve these frontend-local diagnostics as the target behavior:

- existing:
  - `workflow_boundary_type_invalid`
  - `workflow_signature_mismatch`
  - `json_surface_unsupported`
  - `source_map_missing`
- new, if current taxonomy has no precise equivalent:
  - `workflow_boundary_projection_collision`
  - `workflow_boundary_projection_missing_origin`

The new build artifact must be deterministic and compiler-owned:

```json
{
  "schema_version": "workflow_lisp_boundary_projection.v1",
  "entry_workflow": "neurips/entry::orchestrate",
  "workflows": [
    {
      "workflow_name": "neurips/entry::orchestrate",
      "display_name": "orchestrate",
      "params": [
        {"name": "input", "type_kind": "record"},
        {"name": "report_path", "type_kind": "relpath"}
      ],
      "return_kind": "union",
      "flattened_inputs": [
        {
          "generated_name": "input__summary__report",
          "source_path": ["input", "summary", "report"],
          "contract_definition": {"kind": "relpath", "type": "relpath", "under": "artifacts/work"}
        }
      ],
      "flattened_outputs": [
        {
          "generated_name": "return__variant",
          "source_path": ["return", "variant"],
          "contract_definition": {"kind": "scalar", "type": "enum"}
        }
      ],
      "generated_internal_inputs": [
        {
          "generated_name": "__write_root__provider_attempt__attempt__result_bundle",
          "reason": "managed_write_root"
        }
      ]
    }
  ]
}
```

The exact JSON ordering can follow the existing build serializer style, but the payload must include:

- workflow identity;
- structured param summary and return kind;
- authored flattened input/output mappings with `source_path` and `contract_definition`;
- internal generated inputs separate from authored flattened params.

## Task 1: Re-Baseline The Tests Around The Approved Projection Contract

**Files:**

- Modify: `tests/test_workflow_lisp_structured_results.py`
- Modify: `tests/test_workflow_lisp_workflows.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] **Step 1: Replace stale assertions with projection-contract assertions**

Update existing tests so they assert the approved structured-authority model instead of older informal flattening assumptions:

- workflow signatures remain structured even when lowered outputs are flat;
- union workflow returns are still accepted where `UnionWorkflowBoundaryProjection` is the approved compatibility bridge;
- imported bundle signature matching still reasons from structured types, not flat-name authority.

- [ ] **Step 2: Add failing tests for new projection obligations**

Add focused tests that fail on the current tree for:

- deterministic collision rejection during recursive record flattening;
- explicit separation between authored flattened inputs and generated internal write-root inputs;
- provenance coverage for every flattened authored input/output emitted by lowering;
- dedicated emission of `workflow_boundary_projection.json` plus manifest registration.

Suggested test names:

```python
test_workflow_signature_contract_flattening_rejects_projection_name_collisions
test_lowering_origin_map_separates_authored_inputs_from_generated_internal_inputs
test_lower_workflow_definitions_reuses_projection_metadata_for_union_call_outputs
test_build_emits_workflow_boundary_projection_artifact
```

- [ ] **Step 3: Prefer inline tmp_path fixtures for narrow failure cases**

For collision and missing-origin tests, use small inline `.orc` modules written under `tmp_path` instead of adding permanent fixtures unless a focused test becomes unreadable.

- [ ] **Step 4: Run collect-only before implementation**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_build_artifacts.py -q
```

Expected:

- all four modules collect successfully;
- the new projection tests appear in collection output.

## Task 2: Formalize Workflow-Boundary Projection Metadata In Frontend-Owned Contracts

**Files:**

- Modify: `orchestrator/workflow_lisp/contracts.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `tests/test_workflow_lisp_structured_results.py`
- Modify: `tests/test_workflow_lisp_workflows.py`

- [ ] **Step 1: Introduce one workflow-level projection object**

Keep `FlattenedContractField` and `UnionWorkflowBoundaryProjection` as the leaf-level vocabulary, but wrap them in one workflow-level projection structure owned by `contracts.py`. That structure must expose, at minimum:

- canonical workflow name;
- structured param summary;
- return kind (`record` or `union`);
- authored flattened inputs;
- authored flattened outputs;
- generated internal inputs.

Do not make build serialization re-derive this from lowered mappings.

- [ ] **Step 2: Make `derive_workflow_signature_contracts(...)` return both shared contracts and projection metadata**

Refactor the helper so the same derivation pass produces:

- lowered shared-surface `inputs`;
- lowered shared-surface `outputs`;
- deterministic authored boundary projection metadata.

Preserve the current union-return projection behavior, but stop treating the flat field list alone as the authoritative representation.

- [ ] **Step 3: Reject generated-name collisions deterministically**

During recursive record flattening and union projection assembly:

- detect same-name collisions across distinct authored `source_path`s;
- allow only the already-approved union-projection sharing behavior where one projected field is intentionally represented once;
- raise `workflow_boundary_projection_collision` with both authored paths in the diagnostic instead of silently overwriting entries.

- [ ] **Step 4: Reuse the same projection helper for imported bundle signature matching**

Update `workflows.py` helpers such as `_flattened_boundary_contracts(...)` so they normalize through the same projection metadata path rather than maintaining a second flattening vocabulary. Keep `WorkflowSignature` structured and canonical throughout.

- [ ] **Step 5: Thread projection metadata through compile results without re-derivation**

Extend the frontend-owned compile/lowered result surface so `build.py` can serialize projection metadata directly from compile results. The narrowest acceptable seam is:

- add projection metadata to `LoweredWorkflow`; or
- add an adjacent frontend-owned compile result field that maps workflow name to projection metadata.

Prefer the option that avoids duplicate lookup tables while keeping ownership local to `orchestrator/workflow_lisp/`.

- [ ] **Step 6: Run the focused contract/workflow tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_structured_results.py -k 'workflow_signature_contract_flattening or union_boundary_projection' -q
python -m pytest tests/test_workflow_lisp_workflows.py -k 'union_workflow_returns or unsupported_workflow_param_types or unsupported_workflow_return_fields' -q
```

Expected:

- new collision/projection tests pass;
- supported union workflow returns remain supported;
- unsupported boundary-type diagnostics remain unchanged unless one new projection-specific code is intentionally added.

## Task 3: Thread Projection Metadata Through Lowering And Provenance

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_structured_results.py`
- Modify only if needed: `orchestrator/workflow_lisp/diagnostics.py`

- [ ] **Step 1: Make lowering consume projection metadata instead of recomputing flat names ad hoc**

Use the workflow-level projection object when lowering:

- shared workflow `inputs`;
- shared workflow `outputs`;
- call-boundary flattened refs;
- terminal record projection outputs.

Any helper that currently reconstructs flattened names from types during lowering should either consume the projection metadata directly or prove that the helper is only a local serializer over that metadata.

- [ ] **Step 2: Separate authored flattened inputs from generated internal write-root inputs in provenance**

Preserve backward-compatible remapping behavior, but stop lumping authored and internal inputs together semantically. The recommended shape is:

- keep merged lookup behavior for validation remapping;
- add explicit authored-vs-internal classification in frontend-owned lowering metadata so the build artifact can serialize the separation truthfully.

One acceptable implementation is:

- dedicated authored/internal input maps inside `LoweringOriginMap` with a merged property for legacy lookup; or
- one map plus explicit classification metadata attached to the projection object and validated against lowering outputs.

- [ ] **Step 3: Enforce provenance completeness for projected fields**

Add one frontend-owned validation pass in lowering or compile assembly that checks:

- every authored flattened input in projection metadata has origin coverage;
- every authored flattened output in projection metadata has origin coverage;
- every generated internal input emitted by lowering has origin coverage.

Raise `workflow_boundary_projection_missing_origin` if any entry is missing, and include the workflow name plus generated field name in the error.

- [ ] **Step 4: Keep shared-validation error remapping stable**

`_remap_validation_message(...)` must continue to map failures mentioning generated boundary names back to the authored workflow span/form path. Do not regress existing `source_map_missing` behavior.

- [ ] **Step 5: Run the focused lowering selectors**

Run:

```bash
python -m pytest tests/test_workflow_lisp_lowering.py -k 'union_returning_same_file_calls or terminal_record_projection_returns or generic_match_outputs' -q
```

Expected:

- same-file calls that cross the flattened compatibility seam still lower successfully;
- terminal record projection returns still point at the correct flat output refs;
- projection-aware match outputs remain deterministic.

## Task 4: Emit The Dedicated Boundary-Projection Build Artifact

**Files:**

- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify only if needed: `orchestrator/workflow_lisp/__init__.py`

- [ ] **Step 1: Add one serializer for workflow-boundary projection data**

Implement a build serializer that consumes the compiler-owned projection metadata and emits:

- `schema_version`;
- `entry_workflow`;
- one deterministic workflow entry per compiled workflow, sorted by canonical name;
- authored flattened inputs/outputs sorted by generated name;
- generated internal inputs sorted by generated name.

Do not scrape this payload from `authored_mapping`, `source_map.json`, or any YAML-like projection.

- [ ] **Step 2: Register the new artifact in build output and manifest**

Update `_write_build_artifacts(...)` and `_build_manifest(...)` so builds emit:

- `workflow_boundary_projection.json`

and expose it through `artifact_paths`. Keep the existing deferred shared-contract status entries intact.

- [ ] **Step 3: Keep `source_map.json` provenance-focused**

Do not turn `source_map.json` into a contract dump. It may continue to show generated input/output/path origins, but the structured-to-flat boundary mapping belongs only in the new artifact.

- [ ] **Step 4: Extend build tests for artifact emission and determinism**

Update build-artifact tests to cover:

- required artifact presence now includes `workflow_boundary_projection.json`;
- manifest includes the new artifact path;
- emitted projection artifact content is stable across identical builds;
- source-trace tests still pass without needing to inspect contract definitions from `source_map.json`.

- [ ] **Step 5: Run focused build-artifact checks**

Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k 'fingerprint or emitted_artifacts or source_map' -q
```

Expected:

- fingerprint stability tests still pass without new special cases;
- required artifact assertions now include `workflow_boundary_projection.json`;
- source-map tests remain green after the new artifact is added.

## Task 5: Final Verification And Smoke Compile

**Files:**

- No code changes in this task

- [ ] **Step 1: Re-run collection after the final test surface settles**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_build_artifacts.py -q
```

Expected:

- collection succeeds for all touched modules;
- no accidental test renames broke the planned selectors.

- [ ] **Step 2: Run the full narrow verification sweep from the architecture bundle**

Run:

```bash
python -m pytest tests/test_workflow_lisp_structured_results.py -k 'workflow_signature_contract_flattening or union_boundary_projection' -q
python -m pytest tests/test_workflow_lisp_workflows.py -k 'union_workflow_returns or unsupported_workflow_param_types or unsupported_workflow_return_fields' -q
python -m pytest tests/test_workflow_lisp_lowering.py -k 'union_returning_same_file_calls or terminal_record_projection_returns or generic_match_outputs' -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k 'fingerprint or emitted_artifacts or source_map' -q
```

Expected:

- all selectors pass;
- no broad unrelated test modules are required for this slice unless one of these selectors exposes missing coverage.

- [ ] **Step 3: Run the frontend compile smoke command that proves artifact emission**

Run:

```bash
python -m orchestrator compile tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix/neurips/entry.orc --entry-workflow orchestrate --source-root tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix --provider-externs-file tests/fixtures/workflow_lisp/cli/providers.json --prompt-externs-file tests/fixtures/workflow_lisp/cli/prompts.json --imported-workflow-bundles-file tests/fixtures/workflow_lisp/cli/imported_workflow_bundles.json --command-boundaries-file tests/fixtures/workflow_lisp/cli/commands.json
```

Expected:

- compile exits successfully;
- the emitted build directory contains `workflow_boundary_projection.json`;
- that artifact includes the selected entry workflow plus both authored flattened boundary fields and `generated_internal_inputs`.

- [ ] **Step 4: Record verification evidence in the implementation handoff**

When implementation is complete, record:

- the exact files changed;
- the exact commands run;
- whether new diagnostics were added;
- where `workflow_boundary_projection.json` was observed in the smoke build.

## Execution Notes

- Keep changes scoped to the frontend-owned boundary-projection seam. Do not opportunistically refactor unrelated lowering or build surfaces.
- Prefer the smallest data-model extension that makes the boundary contract explicit. The goal is to stop implicit behavior, not to invent a second frontend IR.
- If current code diverges from this plan, the approved architecture and this plan win over the drift.
