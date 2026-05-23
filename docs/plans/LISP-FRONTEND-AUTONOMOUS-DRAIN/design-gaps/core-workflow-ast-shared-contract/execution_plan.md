# Core Workflow AST Shared Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the bounded shared `CoreWorkflowAST` contract so validated workflows carry one syntax-neutral post-authoring surface, Workflow Lisp builds emit `core_workflow_ast.json`, and downstream lowering, semantic indexing, explain output, and source-map coverage stop treating Core AST as deferred.

**Architecture:** Keep authored compatibility in `SurfaceWorkflow`, insert `CoreWorkflowAST` immediately after shared authored elaboration, and keep executable/runtime behavior otherwise unchanged. Shared meaning stays under `orchestrator/workflow/`, frontend artifact emission stays under `orchestrator/workflow_lisp/`, and command semantics remain declared metadata only rather than inferred from shell text or reports.

**Tech Stack:** Python dataclasses, `orchestrator.workflow`, `orchestrator.workflow_lisp`, `orchestrator.loader.WorkflowLoader`, existing runtime-plan / semantic-IR / projection builders, pytest, and the checked-in Workflow Lisp CLI fixtures under `tests/fixtures/workflow_lisp/`.

---

## Fixed Inputs

Treat these as implementation authority:

- `docs/index.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/steering.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `45. Core Workflow AST`
  - `46. Validated Core Workflow AST`
  - `47. Semantic IR`
  - `48. Executable IR`
  - `59. Validation Sequence`
  - `72. Lowering Errors`
  - `74. Source Map Requirements`
  - `76. Build Artifacts`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `6. Lowering Contract`
  - `9. Source Spans And Diagnostics`
  - `10. Validation`
  - `14. Implementation Stages`
- `docs/design/workflow_lisp_core_workflow_ast.md`
- `docs/design/workflow_lisp_core_stmt_taxonomy.md`
- `docs/design/workflow_lisp_source_map.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/core-workflow-ast-shared-contract/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-full-restart-20260523T081550Z/iterations/1/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-full-restart-20260523T081550Z/iterations/1/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

Reference existing shared surfaces before editing:

- `orchestrator/workflow/surface_ast.py`
- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/workflow/semantic_ir.py`
- `orchestrator/workflow/runtime_plan.py`
- `orchestrator/workflow/state_projection.py`
- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow_lisp/source_map.py`
- `orchestrator/cli/commands/explain.py`

## Current Repo Baseline

Assume this exact starting point:

- `docs/steering.md` is empty in this checkout and does not widen scope.
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` currently has no events, so infer status from the approved design docs and the checkout, not from ledger history.
- There is no shared `orchestrator/workflow/core_ast.py` module yet.
- `LoadedWorkflowBundle` currently exposes `surface`, `semantic_ir`, `ir`, `projection`, `runtime_plan`, `imports`, and `provenance`, but no `core_workflow_ast`.
- `orchestrator/workflow/lowering.py` still lowers `SurfaceWorkflow` directly to executable IR and projection and constructs bundles from that direct path.
- `orchestrator/workflow/semantic_ir.py` still derives semantic meaning directly from `SurfaceWorkflow` plus runtime-owned surfaces rather than from a shared Core AST.
- `orchestrator/workflow_lisp/build.py` still emits `semantic_ir.json`, `runtime_plan.json`, `source_map.json`, and related artifacts, but not `core_workflow_ast.json`.
- `orchestrator/workflow_lisp/build.py` still marks `core_workflow_ast` as `deferred_shared_contract`.
- `orchestrator/workflow_lisp/source_map.py` still reports `core_workflow_ast` coverage as `deferred_shared_contract`.
- `orchestrator/cli/commands/explain.py` still prints `Deferred artifacts: core_workflow_ast`.
- `tests/test_workflow_core_ast.py` does not exist yet.

Execution rule for this plan: if current code diverges from the approved architecture, the architecture and the tests written from this plan win.

## Hard Scope Limits

Implement only the selected `core-workflow-ast-shared-contract` slice:

- add one shared `CoreWorkflowAST` schema, builder, validator, lowering entry point, and serializer under `orchestrator/workflow/`;
- derive Core AST from validated `SurfaceWorkflow` plus imported-bundle metadata and existing provenance, not from frontend syntax objects, debug YAML, runtime logs, pointer files, or report parsing;
- attach Core AST to `LoadedWorkflowBundle` for both YAML-loaded and Workflow Lisp-compiled bundles;
- make executable lowering and semantic-IR derivation consume Core AST as their upstream shared statement catalog;
- emit deterministic `core_workflow_ast.json` for compiled Workflow Lisp builds;
- mark Core AST as emitted and covered in build-manifest, explain, and source-map/runtime-observability surfaces.

Explicit non-goals:

- no new Workflow Lisp language forms, parser changes, stdlib work, module work, macros, or runtime executor redesign;
- no redesign of `SurfaceWorkflow`, `SemanticWorkflowIR`, `WorkflowRuntimePlan`, `ExecutableWorkflow`, queue behavior, provider execution, or pointer-authority rules;
- no YAML generation, no second execution engine, and no fabricated symmetry artifacts beyond the real Core AST contract;
- no command-text inspection, report parsing, pointer-as-state recovery, or hidden shell semantics;
- no repo-wide enforcement or unrelated docs migration.

## Non-Negotiable Contracts

Keep these fixed during execution:

- `SurfaceWorkflow` remains the authored validation and compatibility surface.
- `CoreWorkflowAST` becomes the first shared syntax-neutral boundary after authored elaboration.
- `SemanticWorkflowIR`, `WorkflowRuntimePlan`, `ExecutableWorkflow`, and runtime execution stay downstream shared surfaces and are not redesigned in this slice.
- Build Core AST only from validated shared structures:
  `SurfaceWorkflow`,
  imported bundle metadata,
  normalized contracts,
  declared command-boundary metadata,
  and existing provenance/source-map bridge data.
- Core AST must not become a loophole for inline semantic shell or Python glue. `CoreCommandStep` records only declared `external_tool` or `certified_adapter` metadata.
- Every generated Core statement must be source-mappable by stable origin key or validation subject reference; Core coverage cannot be claimed without persisted lineage evidence.
- `lower_surface_workflow(...)` may remain as a compatibility shim, but real lowering authority must move to `lower_core_workflow_ast(...)`.
- `derive_workflow_semantic_ir(...)` must consume Core AST as the authoritative shared statement/contract catalog rather than continuing to treat `SurfaceWorkflow` as the shared semantic boundary.
- `core_workflow_ast.json` must be deterministic and JSON-serializable with a dedicated schema constant such as `CORE_WORKFLOW_AST_SCHEMA_VERSION = "core_workflow_ast.v1"`.

## File Ownership

Create:

- `orchestrator/workflow/core_ast.py`
- `tests/test_workflow_core_ast.py`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/core-workflow-ast-shared-contract/execution_plan.md` (this file)

Modify:

- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/workflow/semantic_ir.py`
- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow_lisp/source_map.py`
- `orchestrator/cli/commands/explain.py`
- `tests/test_workflow_ir_lowering.py`
- `tests/test_loader_validation.py`
- `tests/test_workflow_semantic_ir.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_cli.py`
- `tests/test_runtime_observability.py`
- `tests/test_runtime_observability_cli.py`

Modify only if a focused failing test proves the bridge is required:

- `orchestrator/loader.py`
- `tests/workflow_bundle_helpers.py`

Do not widen ownership into parser, macro, module, queue, state-manager, executor, or unrelated workflow authoring code unless a targeted failing test shows this slice cannot complete without a narrow compatibility change.

## Required Core AST Contract

Implement one shared module that owns the initial contract, validation, lowering bridge, and serialization even if some statement classes are lightweight wrappers over existing normalized data.

Required public surface:

- `CORE_WORKFLOW_AST_SCHEMA_VERSION = "core_workflow_ast.v1"`
- dataclasses for:
  - `CoreWorkflowAST`
  - `CoreWorkflowImport`
  - `CoreWorkflowContract`
  - `CoreStmtMeta`
  - statement records for the currently implemented shared step families
- public functions:
  - `build_core_workflow_ast(surface, imports, provenance)`
  - `validate_core_workflow_ast(core_workflow_ast, *, imports)`
  - `lower_core_workflow_ast(core_workflow_ast)`
  - `workflow_core_ast_to_json(core_workflow_ast)`

Required shape for the first implementation:

- one workflow-level object carrying:
  - workflow name
  - DSL version
  - normalized inputs / outputs / artifacts / providers
  - normalized imported workflow metadata
  - ordered body statements
  - explicit finalization statements or one explicit `CoreFinally` wrapper
  - source-map bridge data sufficient to serialize stable Core node lineage
- one closed statement taxonomy covering the currently implemented shared authored step kinds:
  - command
  - provider
  - adjudicated provider
  - wait-for
  - assert
  - set-scalar
  - increment-scalar
  - materialize-artifacts
  - select-variant-output
  - call
  - if
  - match
  - for-each
  - repeat-until
- statement metadata that always includes:
  - stable statement id
  - authored step id
  - step kind
  - display name when available
  - lexical scope / structured region identity where relevant
  - source-map origin key or equivalent bridge handle
  - generated-by metadata when a structured construct expands nested statements

Implementation rules:

- map existing `SurfaceStepKind` values one-for-one into shared Core statement kinds for this slice; do not invent new author-facing forms;
- preserve authored order and stable ids so downstream bundle projections and explain output remain deterministic;
- keep contracts and refs normalized in Core AST, but do not redesign the full validated reference catalog in this slice;
- validate that every Core statement can be explained back to a source origin before accepting the object;
- lower executable IR and projection from Core AST, not directly from `SurfaceWorkflow`.

## Task 1: Lock The Shared Core AST Contract With Failing Tests

**Files:**

- Create: `tests/test_workflow_core_ast.py`
- Modify: `tests/test_workflow_ir_lowering.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_workflow_semantic_ir.py`

- [ ] **Step 1: Add focused YAML-bundle tests for the new shared surface**

Create `tests/test_workflow_core_ast.py` using small YAML fixtures in `tmp_path`. Cover at least these cases:

- YAML-loaded bundles expose `bundle.core_workflow_ast`;
- `bundle.core_workflow_ast.schema_version == "core_workflow_ast.v1"`;
- statement order and statement kinds match authored order for representative workflows with command, provider, `if`, `match`, and `call`;
- imported workflow aliases and workflow metadata are preserved on the Core AST surface;
- command-boundary facts record only declared `boundary_kind` / `boundary_name` metadata, not parsed shell text.

Recommended test names:

- `test_build_core_workflow_ast_from_yaml_bundle_records_statement_order_and_metadata`
- `test_core_ast_helper_returns_shared_surface_from_loaded_bundle`
- `test_core_ast_validation_rejects_missing_source_map_origin`

- [ ] **Step 2: Extend existing bundle/lowering tests before implementation**

Update existing tests so they fail first for the new boundary:

- `tests/test_loader_validation.py` should assert `LoadedWorkflowBundle` has `core_workflow_ast`;
- `tests/test_workflow_ir_lowering.py` should assert the executable lowering path is reachable from `lower_core_workflow_ast(...)`;
- `tests/test_workflow_semantic_ir.py` should assert semantic-IR statement order and bridge metadata still hold after the builder is switched to Core AST.

- [ ] **Step 3: Add a lowering-equivalence characterization test**

In `tests/test_workflow_ir_lowering.py`, add one representative fixture asserting that lowering the bundle's Core AST yields the same executable node ids, projection node bindings, and runtime-plan ordering as the current surface-based path for the same workflow. This locks in the "new seam, unchanged runtime behavior" contract.

- [ ] **Step 4: Run collection and the narrow shared-surface selectors**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_core_ast.py -q
python -m pytest tests/test_workflow_core_ast.py tests/test_workflow_ir_lowering.py tests/test_loader_validation.py tests/test_workflow_semantic_ir.py -k "core_workflow_ast or lower_core_workflow_ast or loaded_bundle or semantic_ir" -q
```

Expected:

- collection succeeds once the new test module exists;
- the test run fails because `orchestrator/workflow/core_ast.py`, `LoadedWorkflowBundle.core_workflow_ast`, and the new lowering path do not exist yet.

## Task 2: Implement `CoreWorkflowAST` And Thread It Through The Shared Bundle

**Files:**

- Create: `orchestrator/workflow/core_ast.py`
- Modify: `orchestrator/workflow/loaded_bundle.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `tests/test_workflow_core_ast.py`
- Modify: `tests/test_loader_validation.py`

- [ ] **Step 1: Implement the shared Core AST dataclasses, builder, validator, and serializer**

In `orchestrator/workflow/core_ast.py`:

- add the schema constant and public dataclasses;
- build Core AST from `SurfaceWorkflow`, imported bundle metadata, and provenance only;
- validate authored-order stability, supported statement kinds, imported alias consistency, and source-map coverage presence;
- add deterministic JSON serialization used by build artifacts and explain output.

Use `WorkflowValidationError` with the existing lowering taxonomy surface when validation fails. Prefer a dedicated failure such as `core_ast_invalid` rather than silent fallback.

- [ ] **Step 2: Extend `LoadedWorkflowBundle` and helper accessors**

In `orchestrator/workflow/loaded_bundle.py`:

- add `core_workflow_ast` to `LoadedWorkflowBundle`;
- add a helper such as `workflow_core_workflow_ast(workflow_or_bundle)` mirroring the existing typed helper pattern;
- preserve existing helpers and bundle immutability semantics.

- [ ] **Step 3: Insert the Core AST seam into bundle construction**

In `orchestrator/workflow/lowering.py`:

- build Core AST before executable lowering inside `build_loaded_workflow_bundle(...)`;
- make `lower_core_workflow_ast(...)` the real executable/projection lowering entry point;
- keep `lower_surface_workflow(...)` only as a compatibility shim that first builds Core AST, then delegates to the Core lowerer;
- keep `build_loaded_workflow_bundle(...)` returning the same runtime surfaces plus the new Core AST field.

- [ ] **Step 4: Re-run the shared Core AST test slice**

Run:

```bash
python -m pytest tests/test_workflow_core_ast.py tests/test_loader_validation.py -k "core_workflow_ast or loaded_bundle" -q
```

Expected: the new Core AST bundle tests pass, while downstream semantic/build surfaces may still fail until later tasks land.

## Task 3: Rebase Downstream Shared Derivation On Core AST

**Files:**

- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/workflow/semantic_ir.py`
- Modify: `tests/test_workflow_ir_lowering.py`
- Modify: `tests/test_workflow_semantic_ir.py`

- [ ] **Step 1: Make semantic derivation consume Core AST explicitly**

Change `derive_workflow_semantic_ir(...)` so its authoritative workflow/statement input is `core_workflow_ast`, not `surface`. Keep `surface` out of the builder unless one remaining compatibility field is still unavailable from Core AST and the test proves the bridge is necessary.

- [ ] **Step 2: Build semantic statement catalogs from Core AST ids and metadata**

Update semantic-IR statement, effect, prompt-surface, command-boundary, and call-edge derivation so:

- statement ids come from Core AST statement ids;
- step kind and authored order follow Core AST ordering;
- command-boundary metadata is copied from `CoreCommandStep` declared metadata only;
- executable bridges still map every runtime node back to a Core statement / origin path.

- [ ] **Step 3: Preserve runtime behavior while switching the seam**

Keep executable node ids, projection bindings, runtime-plan ordering, and semantic-IR schema version unchanged for representative existing workflows. This task is complete only when the old direct-surface path is no longer the source of truth.

- [ ] **Step 4: Run the focused lowering and semantic selectors**

Run:

```bash
python -m pytest tests/test_workflow_core_ast.py tests/test_workflow_ir_lowering.py tests/test_workflow_semantic_ir.py tests/test_loader_validation.py -k "core_workflow_ast or semantic_ir or lower_core_workflow_ast" -q
```

Expected: the shared lowering and semantic bundle tests pass with Core AST as the upstream authority.

## Task 4: Emit `core_workflow_ast.json` And Remove Deferred-Core Surfaces

**Files:**

- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `orchestrator/workflow_lisp/source_map.py`
- Modify: `orchestrator/cli/commands/explain.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_cli.py`
- Modify: `tests/test_runtime_observability.py`
- Modify: `tests/test_runtime_observability_cli.py`

- [ ] **Step 1: Emit the new build artifact and manifest status**

In `orchestrator/workflow_lisp/build.py`:

- write `core_workflow_ast.json` alongside the existing build artifacts;
- add it to `artifact_paths`;
- serialize from `validated_bundle.core_workflow_ast`;
- change manifest status from `deferred_shared_contract` to `emitted`.

- [ ] **Step 2: Make source-map coverage honest for Core AST**

In `orchestrator/workflow_lisp/source_map.py`:

- change `SOURCE_MAP_COVERAGE["core_workflow_ast"]` to `"covered"`;
- add a persisted per-workflow `core_nodes` lineage section that maps stable Core statement ids to origin keys or equivalent bridge handles;
- validate that every serialized Core statement has lineage before coverage is reported as covered.

Update runtime-observability expectations to reflect the new coverage value.

- [ ] **Step 3: Replace the deferred-artifact explain banner with a Core AST view**

In `orchestrator/cli/commands/explain.py`:

- stop printing `Deferred artifacts: core_workflow_ast`;
- add a `Core Workflow AST:` section before `Semantic IR:`;
- keep the explain payload deterministic and limited to the selected workflow/form rather than dumping unrelated bundle data.

- [ ] **Step 4: Update build, CLI, and observability assertions**

Adjust tests so they assert:

- `core_workflow_ast.json` exists;
- manifest and runtime observability mark Core AST as emitted / covered;
- explain output contains a Core AST section and no deferred-Core banner;
- source-map documents expose the new `core_nodes` lineage section for compiled Workflow Lisp workflows.

- [ ] **Step 5: Run the focused build/CLI/observability selectors**

Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_cli.py -k "core_workflow_ast or explain or emitted_artifacts" -q
python -m pytest tests/test_runtime_observability.py tests/test_runtime_observability_cli.py -k "core_workflow_ast or source_map_coverage or compiled_frontend" -q
```

Expected: build, explain, and runtime-observability surfaces stop treating Core AST as deferred.

## Task 5: Final Verification And Compile Smoke

**Files:**

- No new ownership; use the files touched above.

- [ ] **Step 1: Re-run the recorded narrow verification commands**

Run exactly:

```bash
python -m pytest --collect-only tests/test_workflow_core_ast.py -q
python -m pytest tests/test_workflow_core_ast.py -q
python -m pytest tests/test_workflow_ir_lowering.py tests/test_loader_validation.py -k "core_workflow_ast or loaded_bundle or lower_surface_workflow" -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_cli.py -k "core_workflow_ast or explain or emitted_artifacts" -q
python -m pytest tests/test_runtime_observability.py tests/test_runtime_observability_cli.py -k "core_workflow_ast or source_map_coverage or compiled_frontend" -q
```

- [ ] **Step 2: Run one frontend compile smoke command that proves artifact emission**

Run:

```bash
python -m orchestrator compile tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix/neurips/entry.orc --entry-workflow orchestrate --source-root tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix --provider-externs-file tests/fixtures/workflow_lisp/cli/providers.json --prompt-externs-file tests/fixtures/workflow_lisp/cli/prompts.json --imported-workflow-bundles-file tests/fixtures/workflow_lisp/cli/imported_workflow_bundles.json --command-boundaries-file tests/fixtures/workflow_lisp/cli/commands.json
```

Expected:

- compile succeeds;
- `.orchestrate/build/<fingerprint>/core_workflow_ast.json` exists;
- the emitted manifest marks `core_workflow_ast` as `emitted`;
- `source_map.json` marks `core_workflow_ast` as `covered`.

- [ ] **Step 3: Record completion evidence in the implementation summary**

When execution is done, record:

- which files changed;
- which focused selectors passed;
- the build root used for the compile smoke;
- the exact evidence that `core_workflow_ast.json` was emitted and explain output no longer lists Core AST as deferred.

Do not claim completion from inspection alone. Completion requires fresh command output from the commands above.
