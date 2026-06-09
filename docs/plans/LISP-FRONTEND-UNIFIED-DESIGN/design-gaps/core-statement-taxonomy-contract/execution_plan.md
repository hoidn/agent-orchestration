# Core Statement Taxonomy Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Workflow Lisp Core statement taxonomy explicit and current-checkout-aligned by updating the internal contract doc, locking the base-family and attached-facet inventory with focused tests, and making only the minimal shared-surface adjustments needed to expose the already-implemented semantics.

**Architecture:** Keep `orchestrator/workflow/core_ast.py` as the authority for base statement-family identity, and treat command boundaries, publications, snapshots, proof requirements, managed write roots, promoted semantic effects, runtime-plan operations, and source-map lineage as attached semantic facets derived by existing shared modules. Implement this slice by rewriting `docs/design/workflow_lisp_core_stmt_taxonomy.md` around the current base-family-plus-facet model, then tighten shared tests across `core_ast`, `semantic_ir`, `runtime_plan`, build artifacts, and observability so the contract is executable instead of implicit. Do not add new `CoreStmt` dataclasses, a new registry module, new runtime behavior, or a second lowering path.

**Tech Stack:** Markdown design docs under `docs/design/`, Python dataclasses in `orchestrator/workflow/` and `orchestrator/workflow_lisp/`, pytest, existing YAML test helpers, existing Workflow Lisp fixtures, and shared loader/build/runtime-plan surfaces.

---

## Fixed Inputs

Treat these as implementation authority:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_lisp_unified_frontend_design.md`
  - `35. Core Statement Taxonomy Contract`
  - `36. Semantic Workflow IR Contract`
  - `40. Effect Graph Contract`
  - `41. Proof Graph Contract`
  - `42. State Layout Contract`
  - `43. Source Map Contract`
  - `46. Acceptance Gate for Component Architecture`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `0. Prerequisites, Boundaries, And Missing Internal Specs`
  - `45. Core Workflow AST`
  - `46. Validated Core Workflow AST`
  - `47. Semantic IR`
  - `48. Executable IR`
  - `53-58. Lowering rules touching provider, command, call, match, loop, and stdlib forms`
  - `59. Validation Sequence`
  - `63-66. Variant, snapshot, pointer, and report-authority validation`
  - `74. Source Map Requirements`
- `docs/design/workflow_lisp_core_workflow_ast.md`
- `docs/design/workflow_lisp_core_stmt_taxonomy.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/work_instructions.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/core-statement-taxonomy-contract/implementation_architecture.md`
- `state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/3/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/3/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-UNIFIED-DESIGN/progress_ledger.json`

## Current Repo Baseline

Assume this exact starting point:

- `state/LISP-FRONTEND-UNIFIED-DESIGN/progress_ledger.json` currently has no events.
- `docs/steering.md` is empty in this checkout and does not widen scope.
- `docs/design/workflow_lisp_core_stmt_taxonomy.md` still reflects an older one-row-per-family draft that names `CorePreSnapshot`, `CoreConsumeBundle`, `CorePublish`, and `CoreResourceTransitionCandidate` as standalone families, and it does not inventory `CoreForEach`.
- `orchestrator/workflow/core_ast.py` already defines the current shared base statement dataclasses and structural blocks:
  - `CoreCommandStep`
  - `CoreProviderStep`
  - `CoreAdjudicatedProviderStep`
  - `CoreWaitForStep`
  - `CoreAssertStep`
  - `CoreSetScalarStep`
  - `CoreIncrementScalarStep`
  - `CoreMaterializeArtifactsStep`
  - `CoreSelectVariantOutputStep`
  - `CoreCallStep`
  - `CoreIf`
  - `CoreMatch`
  - `CoreForEach`
  - `CoreRepeatUntil`
  - `CoreBranchBlock`
  - `CoreMatchCaseBlock`
  - `CoreFinally`
- `orchestrator/workflow/semantic_ir.py` already projects statement rows, call edges, prompt surfaces, command boundaries, promoted adapter effects, promoted generated effects, proof entries, and managed-write-root state-layout entries from the current base families plus attached metadata.
- `orchestrator/workflow/runtime_plan.py` already derives publication, snapshot, and variant-selection projections from executable/common surfaces keyed back to statement and node identities.
- `orchestrator/workflow_lisp/source_map.py` already validates core-node coverage, executable-node coverage, generated-effect lineage, command-boundary lineage, and generated internal input lineage for compiled frontend builds.
- `orchestrator/workflow_lisp/build.py` already emits `core_workflow_ast.json`, `semantic_ir.json`, `runtime_plan.json`, and `source_map.json`; this slice is missing explicit contract alignment, not emitted artifacts.
- `tests/test_workflow_core_ast.py` currently covers statement order, metadata, helper access, and missing `origin_key` rejection, but it does not yet lock the full base-family inventory or structural-block contract.
- `tests/test_workflow_semantic_ir.py`, `tests/test_workflow_lisp_build_artifacts.py`, `tests/test_runtime_observability.py`, and `tests/test_runtime_observability_cli.py` already cover several attached facets individually, but they do not yet act together as one explicit taxonomy-contract regression net.

## Hard Scope Limits

Implement only the selected `core-statement-taxonomy-contract` slice:

- rewrite the internal statement-taxonomy doc so it matches the current checkout;
- add focused tests that pin the current base statement-family inventory;
- add focused tests that pin the current attached semantic facets and their projections across Semantic IR, runtime plan, source map, and observability;
- make only the smallest shared-module edits required to expose already-implemented contract facts when a focused failing test proves a gap.

Explicit non-goals:

- no new `CoreStmt` dataclasses, executable node kinds, runtime-plan node kinds, or runtime-native effects;
- no redesign of runtime behavior, write-root policy, pointer authority, proof semantics, state layout, or stdlib lowering;
- no new machine-readable taxonomy registry module;
- no helper scripts, inline Python/shell glue, or report-parsing authority changes;
- no edits to progress ledgers, queue state, or unrelated design docs;
- no reopening of already-implemented `ProcRef` / `bind-proc`, runtime-closure, macro, or executable-IR slices.

## File Ownership

Modify:

- `docs/design/workflow_lisp_core_stmt_taxonomy.md`
- `tests/test_workflow_core_ast.py`
- `tests/test_workflow_semantic_ir.py`
- `tests/test_loader_validation.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_runtime_observability.py`
- `tests/test_runtime_observability_cli.py`

Modify only if a focused failing test proves it is required:

- `orchestrator/workflow/core_ast.py`
- `orchestrator/workflow/semantic_ir.py`
- `orchestrator/workflow/runtime_plan.py`
- `orchestrator/workflow/executable_ir.py`
- `orchestrator/workflow_lisp/source_map.py`
- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow/loaded_bundle.py`

Do not widen ownership into parser, reader, macro, typechecker, procedure, or runtime executor modules. This slice is about contract visibility and verification, not new language/runtime semantics.

## Required Contract To Implement

The implementation must leave these rules explicit and unchanged:

- Base statement-family identity comes from the actual shared dataclasses in `orchestrator/workflow/core_ast.py`.
- Attached semantic facets are current implementation surfaces carried through `common` metadata, executable configs, runtime-plan projections, Semantic IR projections, generated internal inputs, and source-map lineage; they are not new standalone statement families unless the shared implementation changes in a future reviewed slice.
- `CoreCommandStep` remains valid only for external tools or certified adapters, and command-boundary meaning must stay aligned with `docs/design/workflow_command_adapter_contract.md`.
- `CoreForEach` is part of the current shared family inventory and must appear in the contract and test net.
- Publication, `variant_output`, `pre_snapshot`, durable variant selection, promoted `resource_transition` / `ledger_update`, promoted `snapshot_capture` / `pointer_materialization`, and reusable-boundary managed write roots remain attached facets with explicit owners.
- Source maps, runtime-plan summaries, build artifacts, and observability remain derived projections; none may become semantic authority.
- Reports remain views, pointer files remain representations, and artifact/path values remain authoritative structured state.

## Task 1: Rewrite The Internal Taxonomy Doc Around The Current Base-Family Plus Facet Model

**Files:**

- Modify: `docs/design/workflow_lisp_core_stmt_taxonomy.md`

- [ ] Replace the outdated standalone-family inventory with a current-checkout-aligned structure that explicitly separates:
  - current shared base statement families;
  - structural nested blocks;
  - attached semantic facets;
  - validation/runtime ownership.
- [ ] Add a section that explains the drift from the older draft instead of silently preserving outdated names.
  - It must call out at least:
    - `CoreForEach` is real and belongs in the base-family inventory;
    - `publish`, `consume_bundle`, `variant_output`, and `pre_snapshot` are current attached facets rather than standalone `CoreStmt` dataclasses;
    - `resource_transition` is currently represented through certified-adapter command boundaries and promoted Semantic IR effects, not a `CoreResourceTransitionCandidate` dataclass.
- [ ] Add one statement-family contract matrix whose columns match the implementation architecture:
  - inputs;
  - outputs or projections;
  - effects;
  - proof or scope behavior;
  - state or write-root behavior;
  - source-map fields;
  - ownership.
- [ ] Keep the doc explicitly internal and implementation-aligned. Do not restate the entire umbrella frontend spec or imply a public DSL contract change.
- [ ] Keep `docs/design/workflow_command_adapter_contract.md` cited as the authority for command/adaptor semantics and runtime-native-promotion boundaries.

**Blocking verification after Task 1:**

- [ ] Run:
  ```bash
  rg -n "^# Workflow Lisp Core Statement Taxonomy$|^## Current Shared Base Statement Families$|^## Structural Nested Blocks$|^## Attached Semantic Facets$|^## Statement-Family Contract Matrix$|^## Drift From Older Draft$" docs/design/workflow_lisp_core_stmt_taxonomy.md
  ```
- [ ] Run:
  ```bash
  rg -n "CoreForEach|workflow_command_adapter_contract\\.md|resource_transition|pointer_materialization|snapshot_capture|pre_snapshot|variant_output|publishes" docs/design/workflow_lisp_core_stmt_taxonomy.md
  ```

Expected after Task 1: the doc describes the current implementation model directly and no longer implies that obsolete standalone-family names are the authoritative current checkout inventory.

## Task 2: Lock The Base Statement-Family Inventory And Structural-Block Contract In Shared Tests

**Files:**

- Modify: `tests/test_workflow_core_ast.py`

- [ ] Extend `tests/test_workflow_core_ast.py` with one focused taxonomy-inventory regression that asserts the current shared base-family order or set comes from the emitted `core_workflow_ast` surface, not the older doc wording.
- [ ] Build or extend one inline YAML fixture in the test module so it exercises at least:
  - one command boundary;
  - one provider boundary;
  - one call boundary;
  - one branch container;
  - one match container;
  - one loop container;
  - one materialization or selection surface.
- [ ] Add assertions for structural blocks:
  - `CoreBranchBlock` preserves branch-local step ids and outputs;
  - `CoreMatchCaseBlock` preserves case-local step ids and outputs;
  - `CoreFinally` preserves finalization statement order when present.
- [ ] Keep source-map lineage expectations explicit:
  - every emitted statement still has `meta.id`, `meta.step_id`, and non-empty `meta.origin_key`;
  - nested statements remain reachable through the existing core-statement traversal helpers.
- [ ] Prefer inline YAML helpers or existing test helpers over new fixture files unless an inline fixture becomes unmanageable.

Suggested selector names:

- `test_core_ast_records_current_base_statement_family_inventory`
- `test_core_ast_structural_blocks_preserve_nested_lineage`

**Blocking verification after Task 2:**

- [ ] Run:
  ```bash
  python -m pytest --collect-only tests/test_workflow_core_ast.py -q
  ```
- [ ] Run:
  ```bash
  python -m pytest \
    tests/test_workflow_core_ast.py::test_build_core_workflow_ast_from_yaml_bundle_records_statement_order_and_metadata \
    tests/test_workflow_core_ast.py::test_core_ast_records_current_base_statement_family_inventory \
    tests/test_workflow_core_ast.py::test_core_ast_structural_blocks_preserve_nested_lineage -q
  ```

Expected before implementation: the new or tightened selectors fail because the current checkout does not yet lock the full base-family and structural-block inventory explicitly in the test suite.

## Task 3: Lock Attached Semantic Facets Across Semantic IR, Loader Validation, And Frontend Build Artifacts

**Files:**

- Modify: `tests/test_workflow_semantic_ir.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] Extend `tests/test_workflow_semantic_ir.py` so the taxonomy contract is explicit across attached facets rather than inferred from scattered assertions.
- [ ] Add or tighten one regression that proves command-boundary facets stay explicit:
  - `command_call` effects keep `boundary_kind` and `boundary_name`;
  - provider prompt surfaces remain visible for provider families;
  - call-edge projections remain visible for call families.
- [ ] Add or tighten one regression that proves proof and state-layout facets stay explicit:
  - `CoreMatch`-driven proof entries remain recorded in Semantic IR;
  - managed write-root inputs or other deterministic layout entries remain present in `state_layout`.
- [ ] Keep promoted semantic effects covered through existing compiled fixtures:
  - `resource_transition`
  - `ledger_update`
  - `snapshot_capture`
  - `pointer_materialization`
- [ ] Extend `tests/test_loader_validation.py` only where needed to prove attached facets still validate through shared validation rather than through ad hoc runtime behavior.
  - Reuse existing version-gate and shape-validation selectors for:
    - `variant_output`
    - `pre_snapshot`
    - `select_variant_output`
    - `publishes`
- [ ] Extend `tests/test_workflow_lisp_build_artifacts.py` so emitted JSON artifacts remain aligned with the taxonomy:
  - `core_workflow_ast.json` carries current statement kinds;
  - `semantic_ir.json` carries promoted effects, command boundaries, and call edges;
  - `source_map.json` carries generated internal input and generated-effect lineage required by the attached-facet model.

Suggested selector names:

- `test_semantic_ir_projects_statement_taxonomy_facets`
- `test_build_artifacts_preserve_statement_taxonomy_facet_lineage`

**Blocking verification after Task 3:**

- [ ] Run:
  ```bash
  python -m pytest --collect-only \
    tests/test_workflow_semantic_ir.py \
    tests/test_loader_validation.py \
    tests/test_workflow_lisp_build_artifacts.py -q
  ```
- [ ] Run:
  ```bash
  python -m pytest \
    tests/test_workflow_semantic_ir.py::test_derive_semantic_ir_from_yaml_bundle_records_contracts_refs_effects_and_bridges \
    tests/test_workflow_semantic_ir.py::test_frontend_build_semantic_ir_projects_promoted_resource_and_ledger_effects \
    tests/test_workflow_semantic_ir.py::test_frontend_build_semantic_ir_projects_generated_snapshot_and_pointer_effects \
    tests/test_loader_validation.py::test_variant_output_requires_version_2_14 \
    tests/test_loader_validation.py::test_pre_snapshot_digest_must_be_sha256 \
    tests/test_loader_validation.py::test_select_variant_output_evidence_mode_must_be_snapshot_diff \
    tests/test_loader_validation.py::test_v12_publishes_rejected_in_v1_1_1 \
    tests/test_workflow_lisp_build_artifacts.py::test_build_runtime_plan_artifact_matches_selected_workflow_lineage_and_manifest \
    tests/test_workflow_lisp_build_artifacts.py::test_source_map_serializes_generated_semantic_effects_for_frontend_build \
    tests/test_workflow_lisp_build_artifacts.py::test_semantic_ir_artifact_serializes_promoted_effects_for_frontend_build -q
  ```

Expected before implementation: at least one new or tightened selector fails because the repo does not yet treat the taxonomy as a first-class cross-module regression contract.

## Task 4: Lock Runtime-Plan And Observability Alignment For The Same Taxonomy Surface

**Files:**

- Modify: `tests/test_runtime_observability.py`
- Modify: `tests/test_runtime_observability_cli.py`

- [ ] Extend `tests/test_runtime_observability.py` so runtime-plan and observability coverage explicitly align with the base-family plus facet model.
- [ ] Add or tighten one regression that proves command-boundary observability remains keyed to statement and node identity rather than inferred from logs alone.
- [ ] Add or tighten one regression that proves compiled frontend provenance prefers executable-node lineage and runtime-plan ordering derived from the current statement families.
- [ ] Extend `tests/test_runtime_observability_cli.py` only enough to keep one integration-style CLI proof that `.orc` runs still persist compiled-frontend provenance and runtime observability without introducing any new workflow mechanics.

Suggested selector names:

- `test_runtime_observability_preserves_statement_taxonomy_command_boundary_lineage`
- `test_cli_run_persists_compiled_frontend_taxonomy_provenance`

**Blocking verification after Task 4:**

- [ ] Run:
  ```bash
  python -m pytest --collect-only tests/test_runtime_observability.py tests/test_runtime_observability_cli.py -q
  ```
- [ ] Run:
  ```bash
  python -m pytest \
    tests/test_runtime_observability.py::test_compiled_frontend_source_context_logs_certified_adapter_metadata \
    tests/test_runtime_observability.py::test_executor_uses_bundle_runtime_plan_for_top_level_ordering \
    tests/test_runtime_observability.py::test_compiled_frontend_source_context_can_use_runtime_plan_command_hints \
    tests/test_runtime_observability_cli.py::test_run_workflow_persists_compiled_frontend_provenance_for_orc_runs \
    tests/test_runtime_observability_cli.py::test_run_workflow_logs_compiled_frontend_source_context -q
  ```

Expected before implementation: any new taxonomy-specific assertions fail until the regression net explicitly covers runtime-plan and observability ownership for the attached facets.

## Task 5: Make Only The Minimal Shared-Surface Adjustments Required By Failing Tests

**Files:**

- Modify only if required: `orchestrator/workflow/core_ast.py`
- Modify only if required: `orchestrator/workflow/semantic_ir.py`
- Modify only if required: `orchestrator/workflow/runtime_plan.py`
- Modify only if required: `orchestrator/workflow/executable_ir.py`
- Modify only if required: `orchestrator/workflow_lisp/source_map.py`
- Modify only if required: `orchestrator/workflow_lisp/build.py`
- Modify only if required: `orchestrator/workflow/loaded_bundle.py`

- [ ] If Task 2-4 tests expose missing visibility, add the narrowest possible implementation support in the owning shared module.
- [ ] Preferred fixes:
  - expose stable family or facet facts from the module that already owns them;
  - tighten serialization or derived projections only where a tested contract fact is missing;
  - preserve existing validation and runtime ownership boundaries.
- [ ] Forbidden fixes:
  - inventing a new registry module only for the taxonomy;
  - moving facet authority from shared runtime surfaces into docs or debug YAML;
  - back-filling semantics from reports, shell text, or pointer files;
  - broad refactors to unrelated lowering, parser, runtime, or executor code.

**Blocking verification after Task 5:**

- [ ] Re-run every selector from Tasks 2-4 until all pass.
- [ ] If any new tests were added or renamed, re-run:
  ```bash
  python -m pytest --collect-only \
    tests/test_workflow_core_ast.py \
    tests/test_workflow_semantic_ir.py \
    tests/test_loader_validation.py \
    tests/test_workflow_lisp_build_artifacts.py \
    tests/test_runtime_observability.py \
    tests/test_runtime_observability_cli.py -q
  ```

Expected after Task 5: the implementation remains behaviorally unchanged, but the statement-taxonomy contract is now explicit in the doc set and enforced across the existing shared projections.

## Final Verification

- [ ] Run the doc checks from Task 1.
- [ ] Run the focused pytest selectors from Tasks 2-4.
- [ ] Run one broader shared-surface sweep:
  ```bash
  python -m pytest \
    tests/test_workflow_core_ast.py \
    tests/test_workflow_semantic_ir.py \
    tests/test_workflow_lisp_build_artifacts.py \
    tests/test_runtime_observability.py \
    tests/test_runtime_observability_cli.py -q
  ```
- [ ] Run one end-to-end-style integration proof because this slice touches shared runtime/DSL-facing verification surfaces:
  ```bash
  python -m pytest \
    tests/test_workflow_lisp_build_artifacts.py::test_build_result_same_file_validated_bundles_keep_executable_and_runtime_surfaces \
    tests/test_runtime_observability_cli.py::test_run_workflow_persists_compiled_frontend_provenance_for_orc_runs -q
  ```

Implementation is complete only when:

- `docs/design/workflow_lisp_core_stmt_taxonomy.md` matches the current base-family-plus-facet model;
- focused tests explicitly cover the current family inventory and attached semantic facets;
- no new runtime semantics or statement families were introduced;
- visible verification output proves the shared projections and CLI/runtime provenance still agree.
