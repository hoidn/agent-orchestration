# Executable IR Component Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Formalize Workflow Lisp executable IR as a reviewed shared component contract with explicit schema/versioned validation, a real `executable` pipeline checkpoint, and first-class emitted artifact/manifest plus compile/explain export handling while keeping `runtime_plan`, `semantic_ir`, `source_map`, and `workflow_boundary_projection` as derived bridge layers.

**Architecture:** Keep `LoadedWorkflowBundle.ir` / `ExecutableWorkflow` as the only runtime-facing executable authority. Add the executable schema marker, validator, and serializer in `orchestrator/workflow/executable_ir.py`, invoke that validator in shared bundle construction and again from the Workflow Lisp `executable` pass as an idempotent post-`shared_validation` recheck over already-built bundles, and continue deriving `runtime_plan`, `semantic_ir`, and source-map lineage from the validated executable node universe. Preserve the current compatibility path `.orc -> lowered workflow dictionaries -> shared loader/validation -> LoadedWorkflowBundle`; do not add new node kinds, runtime closures, dynamic dispatch, or executor behavior changes.

**Tech Stack:** Python dataclasses, shared workflow runtime modules under `orchestrator/workflow/`, Workflow Lisp compiler/build modules under `orchestrator/workflow_lisp/`, pytest, and the checked-in Workflow Lisp fixture/build surfaces.

---

## Fixed Inputs

Treat these as implementation authority:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `0. Prerequisites, Boundaries, And Missing Internal Specs`
  - `48. Executable IR`
  - `49. Runtime Plan`
  - `59. Validation Sequence`
  - `74. Source Map Requirements`
  - `75. Runtime Observability`
  - `76. Build Artifacts`
- `docs/design/workflow_lisp_unified_frontend_design.md`
  - `37. Executable IR Contract`
  - `43. Source Map Contract`
  - `45. Debug YAML Renderer Contract`
  - `46. Acceptance Gate for Component Architecture`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/work_instructions.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/executable-ir-component-contract/implementation_architecture.md`
- `state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/5/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/5/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-UNIFIED-DESIGN/progress_ledger.json`

## Current Repo Baseline

Assume this exact starting point:

- `state/LISP-FRONTEND-UNIFIED-DESIGN/progress_ledger.json` currently has no events, so do not assume partial implementation from ledger state.
- `docs/steering.md` is empty in this checkout and does not widen scope.
- `orchestrator/workflow/executable_ir.py` already defines the shared executable node/config/address dataclasses and `ExecutableWorkflow`, but it does not yet define a dedicated executable-IR schema constant, validator, or explicit serializer.
- `orchestrator/workflow/lowering.py` already assembles `LoadedWorkflowBundle` with `ir`, `projection`, `runtime_plan`, and `semantic_ir`.
- `orchestrator/workflow/runtime_plan.py` already validates runtime-plan topology, but it assumes executable IR was already validated as a coherent authoritative layer.
- `orchestrator/workflow/loaded_bundle.py` already exposes `runtime_plan`; this slice should not invent a second bundle type.
- `orchestrator/workflow_lisp/compiler.py` already runs `source_map -> shared_validation -> executable`, but the `executable` pass currently only re-runs validated-bundle lineage checks.
- `orchestrator/workflow_lisp/lowering.py` currently owns first-checkpoint shared-validation remap/classification through `_SHARED_VALIDATION_CODE_RE`, `_shared_validation_diagnostic_code(...)`, and `_remapped_shared_validation_diagnostic(...)`; this slice must preserve that ownership for bundle-construction executable-validator failures.
- `orchestrator/workflow_lisp/build.py` already emits `executable_ir.json` and `runtime_plan.json`, but `FrontendBuildManifest.artifact_status` still records only `core_workflow_ast` and `semantic_ir`.
- the supported frontend CLI surface still hard-codes export flags and export-request plumbing for only `core_workflow_ast`, `semantic_ir`, `source_map`, and debug YAML, so `executable_ir` / `runtime_plan` are not yet requestable through `python -m orchestrator compile|explain`.
- `tests/test_workflow_ir_lowering.py`, `tests/test_workflow_semantic_ir.py`, `tests/test_workflow_lisp_build_artifacts.py`, `tests/test_workflow_lisp_diagnostics.py`, and `tests/test_workflow_lisp_lowering.py` already cover the shared executable/runtime-plan/semantic bridge and shared-validation remap surfaces enough to extend/rerun them instead of creating new test modules.

## Hard Scope Limits

Implement only the selected `executable-ir-component-contract` slice:

- one shared executable-IR schema/version contract;
- one shared `validate_executable_workflow(...)` checkpoint for the authoritative runtime-facing IR;
- explicit shared-bundle validation before `runtime_plan` and `semantic_ir` derivation;
- a Workflow Lisp `executable` pass that re-runs shared executable validation over already-validated bundles and then executable-node lineage checks;
- build-manifest/export updates for canonical `executable_ir.json` and `runtime_plan.json`, including the supported compile/explain CLI export surface;
- focused regression coverage for executable-node integrity, compile-time-value erasure, bridge alignment, and emitted artifact status.

Explicit non-goals:

- no direct frontend-to-executable lowering path;
- no new executable node kinds, runtime value types, runtime closures, or dynamic dispatch;
- no runtime executor behavior changes;
- no redesign of Core AST, Semantic IR, pointer authority, state layout, or command-adapter policy;
- no helper scripts, inline Python/shell glue, or report-parsing authority changes;
- no reopening of already-implemented `ProcRef` / `bind-proc` baseline behavior except to reject any leakage into executable/runtime artifacts.

## Non-Negotiable Contracts

Keep these rules fixed throughout implementation:

- `LoadedWorkflowBundle.ir` / `ExecutableWorkflow` is the only executable authority.
- `runtime_plan`, `semantic_ir`, `source_map`, `workflow_boundary_projection`, and debug YAML are derived projections; none may redefine execution semantics.
- `ExecutableWorkflow.version` continues to mean workflow DSL version. The new executable schema version must be separate from DSL version.
- Executable IR may contain only runtime-executable values. No unresolved `ProcRef`, `WorkflowRef`, `let-proc` metadata, syntax objects, source spans, typed frontend nodes, or debug-only payloads may survive into serialized or in-memory executable IR.
- Executable command/provider metadata may only reflect already-declared command-boundary or certified-adapter surfaces. Do not infer semantics from shell text.
- Imported YAML bundles and compiled `.orc` bundles must continue to cross reusable boundaries as validated `LoadedWorkflowBundle` instances.
- Shared-bundle executable defects detected while constructing validated bundles must still fail during `shared_validation`, because bundle construction owns the first executable-validator checkpoint.
- The later Workflow Lisp `executable` pass may reuse `executable_ir_invalid` only for post-`shared_validation` revalidation/remapping of already-built bundles; source-map mismatches and semantic-IR bridge mismatches must keep their existing diagnostic families.

## File Ownership

Modify:

- `orchestrator/workflow/executable_ir.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/build.py`
- `orchestrator/cli/main.py`
- `orchestrator/cli/commands/compile.py`
- `orchestrator/cli/commands/explain.py`
- `tests/test_workflow_ir_lowering.py`
- `tests/test_workflow_semantic_ir.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_diagnostics.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_cli.py`

Modify only if a failing focused test proves it is required:

- `orchestrator/workflow/runtime_plan.py`
- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/workflow/semantic_ir.py`
- `orchestrator/workflow_lisp/source_map.py`
- `tests/test_workflow_state_projection.py`

Do not widen ownership into reader/typechecker/procedure/language-surface modules. This slice is a shared executable contract and build/diagnostic alignment pass.

## Implementation Notes

Use the same implementation style as `core_ast.py` and `semantic_ir.py`:

- add a schema constant, not a magic string;
- keep deterministic serializer functions in the owning shared module;
- raise shared `WorkflowValidationError` / `ValidationError` structures from shared runtime validation code rather than bare `ValueError`;
- keep frontend diagnostic remapping in Workflow Lisp modules instead of teaching shared runtime code about `.orc` spans.

If you add or rename tests, run `pytest --collect-only` on the touched modules before the first targeted selector.

## Task 1: Add The Shared Executable IR Schema, Serializer, And Validator

**Files:**

- Modify: `orchestrator/workflow/executable_ir.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `tests/test_workflow_ir_lowering.py`

- [ ] **Step 1: Write the failing executable-contract tests first**

Extend `tests/test_workflow_ir_lowering.py` with focused coverage that proves the contract is missing today:

- a loaded bundle exposes `bundle.ir.schema_version == "workflow_executable_ir.v1"`;
- a dedicated serializer such as `workflow_executable_ir_to_json(bundle.ir)` emits both:
  - `schema_version == "workflow_executable_ir.v1"`;
  - the existing DSL `version` field unchanged;
- `validate_executable_workflow(bundle.ir)` accepts a valid bundle loaded through `WorkflowLoader`;
- a synthetic broken executable workflow with:
  - an unknown node id in `body_region` or `finalization_region`,
  - a mismatched node kind/config pairing,
  - or an address/contract reference to an unknown node
  fails with `WorkflowValidationError` whose first message starts with `executable_ir_invalid:`.

Prefer synthetic IR mutation with `dataclasses.replace(...)` over new fixture files.

- [ ] **Step 2: Run collection and the narrow lowering selector**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_ir_lowering.py -q
python -m pytest tests/test_workflow_ir_lowering.py -q
```

Expected: collection succeeds, then the lowering test module fails because executable IR has no schema/versioned contract or shared validator yet.

- [ ] **Step 3: Implement the shared executable contract**

In `orchestrator/workflow/executable_ir.py`:

- add `WORKFLOW_EXECUTABLE_IR_SCHEMA_VERSION = "workflow_executable_ir.v1"`;
- add `schema_version: str` to `ExecutableWorkflow`;
- add `workflow_executable_ir_to_json(ir: ExecutableWorkflow) -> dict[str, Any]` so emitted JSON does not depend on the generic frontend `_json_data(...)` path for schema materialization;
- add `validate_executable_workflow(ir: ExecutableWorkflow) -> None` plus private helpers that validate:
  - schema version support;
  - unique node ids and region membership coherence;
  - `body_region`, `finalization_region`, and `finalization_entry_node_id` all reference known nodes in valid regions;
  - node dataclass family matches `ExecutableNodeKind` and allowed `execution_config` family;
  - fallthrough and routed-transfer targets resolve to known nodes;
  - `body_entry_node_id`, nested `body_node_ids`, and call/loop output surfaces resolve when present;
  - `ExecutableContract.source_address` and other bound-address surfaces use only supported address families and known node ids;
  - executable payloads do not contain compile-time-only values or frontend-only objects.

In `orchestrator/workflow/lowering.py`:

- set the new `schema_version` when constructing `ExecutableWorkflow`;
- call `validate_executable_workflow(ir)` in `build_loaded_workflow_bundle(...)` before `derive_workflow_runtime_plan(...)` and `derive_workflow_semantic_ir(...)`;
- keep lowering ownership unchanged: validation is a checkpoint on the current compatibility path, not a second lowerer.

- [ ] **Step 4: Re-run the lowering selector and require a pass**

Run:

```bash
python -m pytest tests/test_workflow_ir_lowering.py -q
```

Expected: PASS with validated executable IR, unchanged runtime-plan semantics, and no new executor behavior.

## Task 2: Turn The Workflow Lisp `executable` Pass Into A Real Contract Checkpoint

**Files:**

- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`
- Modify: `tests/test_workflow_lisp_lowering.py`

- [ ] **Step 1: Add failing executable-pass tests**

Extend `tests/test_workflow_lisp_lowering.py` with a targeted shared-validation remap assertion that proves the first executable-validator checkpoint keeps its existing ownership:

- a shared bundle-construction failure raised before validated bundles exist with `WorkflowValidationError([ValidationError(message="executable_ir_invalid: ...")])` is remapped to:
  - code `executable_ir_invalid`,
  - validation pass `shared_validation`,
  - authority layer `shared_validation`,
  - and an authored `.orc` span rather than an opaque shared-runtime traceback;
- keep the existing `test_compile_stage3_module_remaps_shared_validation_failures` selector in the verification matrix so generic shared-validation remap behavior still passes after this slice.

Extend `tests/test_workflow_lisp_diagnostics.py` with targeted assertions that:

- pass order remains `... -> source_map -> shared_validation -> executable`;
- the `executable` pass invokes shared `validate_executable_workflow(...)` only after validated bundles exist;
- executable revalidation runs before executable-node/source-map lineage completion;
- shared bundle-construction failures raised before validated bundles exist remain classified under `shared_validation`;
- a forced post-`shared_validation` executable revalidation failure is surfaced as:
  - code `executable_ir_invalid`,
  - phase `executable`,
  - validation pass `executable`,
  - and an authored `.orc` location rather than an opaque shared-runtime traceback.

Recommended test shape:

- in `tests/test_workflow_lisp_lowering.py`, trigger the first executable-validator checkpoint on the shared bundle-construction path rather than the later compiler `executable` pass, so the test proves the remap still flows through `workflow_lisp/lowering.py`;
- monkeypatch the compiler-local executable-pass revalidation call site to append to a call log after validated bundles are built;
- monkeypatch that executable-pass-local revalidation seam in a second test to raise `WorkflowValidationError([ValidationError(message=\"executable_ir_invalid: ...\")])`;
- keep a separate assertion that a malformed bundle caught during initial shared bundle construction still surfaces through the existing `shared_validation` route;
- assert the compile pipeline preserves the existing source-map/semantic bridge codes for their own failure cases.

- [ ] **Step 2: Run collection and the diagnostics selector**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_diagnostics.py -q
python -m pytest \
  tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_remaps_shared_validation_failures \
  tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_remaps_executable_ir_shared_validation_failures \
  tests/test_workflow_lisp_diagnostics.py -q
```

Expected: at least one new selector fails because the current checkout does not yet classify first-checkpoint `executable_ir_invalid` messages through the shared-validation remap surface and the `executable` pass still re-runs lineage only.

- [ ] **Step 3: Implement the executable-pass checkpoint and classification**

In `orchestrator/workflow_lisp/compiler.py`:

- import the shared executable validator;
- factor the executable pass into two ordered operations:
  - revalidate every bundle IR in the validated bundle set with `validate_executable_workflow(...)` through one compiler-local executable-pass helper or wrapper;
  - then run the existing executable-node lineage/source-map coverage checks;
- preserve current pass ids and pass ordering in both:
  - `_run_stage3_validation_pipeline(...)`;
  - `_run_stage3_entrypoint_validation_pipeline(...)`.

When executable-pass revalidation fails:

- convert the failure into deterministic `LispFrontendDiagnostic` records instead of surfacing a bare exception;
- preserve authored subject/span remapping when the shared validation error can be tied back to a workflow subject or origin;
- keep initial bundle-construction failures on the existing `shared_validation` route rather than reclassifying them after the fact;
- keep bridge-specific diagnostics (`source_map_*`, `semantic_ir_invalid`) unchanged.

In `orchestrator/workflow_lisp/diagnostics.py`:

- classify `executable_ir_invalid` into the `executable` pass/phase for post-`shared_validation` executable-pass revalidation failures;
- keep pass ordering stable so serialized diagnostics sort after `shared_validation` and before any future post-executable checks.

In `orchestrator/workflow_lisp/lowering.py`:

- extend `_SHARED_VALIDATION_CODE_RE` / `_shared_validation_diagnostic_code(...)` so `executable_ir_invalid` is preserved as a shared-validation diagnostic code when the shared bundle-construction checkpoint raises it;
- keep `_remapped_shared_validation_diagnostic(...)` assigning `validation_pass="shared_validation"` and `authority_layer="shared_validation"` for those first-checkpoint failures;
- do not route bundle-construction executable-validator failures through the later `executable` pass classification path.

- [ ] **Step 4: Re-run the diagnostics selector**

Run:

```bash
python -m pytest \
  tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_remaps_shared_validation_failures \
  tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_remaps_executable_ir_shared_validation_failures \
  tests/test_workflow_lisp_diagnostics.py -q
```

Expected: PASS with explicit executable-pass revalidation coverage, stable diagnostic metadata, and unchanged `shared_validation` ownership for initial bundle-construction failures.

## Task 3: Make Executable IR And Runtime Plan First-Class Build And CLI Artifacts

**Files:**

- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `orchestrator/cli/main.py`
- Modify: `orchestrator/cli/commands/compile.py`
- Modify: `orchestrator/cli/commands/explain.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_cli.py`

- [ ] **Step 1: Add failing build-artifact and CLI export tests**

Extend `tests/test_workflow_lisp_build_artifacts.py` so it asserts:

- emitted `executable_ir.json` contains `schema_version == "workflow_executable_ir.v1"`;
- emitted `runtime_plan.json` still contains `schema_version == "workflow_runtime_plan.v1"`;
- `result.manifest.artifact_status` includes:
  - `"executable_ir": "emitted"`,
  - `"runtime_plan": "emitted"`,
  - alongside the existing emitted `core_workflow_ast` and `semantic_ir` entries;
- compiled imported bundle manifest entries remain validated `LoadedWorkflowBundle` values that expose the new executable schema on `bundle.ir` plus derived `runtime_plan`, rather than raw executable sidecars;
- same-file validated bundles exposed through the build result remain `LoadedWorkflowBundle` values carrying validated executable/runtime-plan surfaces across reusable boundaries;
- `normalize_frontend_artifact_exports(...)` accepts `executable_ir` and `runtime_plan`;
- exported `executable_ir` / `runtime_plan` files copy canonical bytes from `result.artifact_paths[...]` and do not regenerate projections independently.

Extend `tests/test_workflow_lisp_cli.py` so it asserts:

- `create_parser()` accepts `--emit-executable-ir` and `--emit-runtime-plan` for both `compile` and `explain`, with the same optional-path behavior as the existing emit flags;
- `compile_workflow(...)` and `explain_workflow(...)` pass `executable_ir` / `runtime_plan` through `normalize_frontend_artifact_exports(...)`;
- compile/explain exported-artifact summaries report the new artifact names when requested and still avoid emitting them when not requested.

- [ ] **Step 2: Run collection and the build-artifact plus CLI selectors**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_cli.py -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_cli.py -q
```

Expected: failures show that executable IR lacks an explicit serialized schema marker, build/export metadata still underreports the emitted artifacts, and the supported CLI surface cannot yet request the new exports.

- [ ] **Step 3: Implement the build/export alignment**

In `orchestrator/workflow_lisp/build.py`:

- serialize executable IR with `workflow_executable_ir_to_json(validated_bundle.ir)` instead of the generic dataclass dump;
- keep `runtime_plan` serialization unchanged except for any needed deterministic ordering fixes exposed by tests;
- extend `FRONTEND_ARTIFACT_EXPORT_FILENAMES` with `executable_ir` and `runtime_plan`;
- update manifest `artifact_status` to mark `executable_ir` and `runtime_plan` as `"emitted"`;
- keep canonical authority in the build root artifacts: export helpers must copy already-written canonical files, not re-render from in-memory objects with divergent code paths.

In `orchestrator/cli/main.py`:

- add `--emit-executable-ir` and `--emit-runtime-plan` alongside the existing frontend artifact export flags for both `compile` and `explain`;
- keep their parser shape identical to the existing emit flags: repeatable, optional path argument, cwd default filename when omitted.

In `orchestrator/cli/commands/compile.py` and `orchestrator/cli/commands/explain.py`:

- include `emit_executable_ir` and `emit_runtime_plan` when building the `normalize_frontend_artifact_exports(...)` request map;
- preserve current summary/printed output behavior so exported-artifact reports automatically include the new names only when requested;
- do not add a parallel artifact-rendering path in CLI commands; they must continue copying canonical files produced by the build root.

- [ ] **Step 4: Re-run the build-artifact plus CLI selectors**

Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_cli.py -q
```

Expected: PASS with canonical `executable_ir.json`, truthful manifest status entries, stable export-copy behavior, and public compile/explain support for the new artifact exports.

## Task 4: Prove Cross-Layer Bridge Integrity And Run End-To-End Verification

**Files:**

- Modify: `tests/test_workflow_semantic_ir.py`
- Modify only if needed: `orchestrator/workflow/executable_ir.py`
- Modify only if needed: `orchestrator/workflow/runtime_plan.py`
- Modify only if needed: `orchestrator/workflow/loaded_bundle.py`
- Modify only if needed: `orchestrator/workflow/semantic_ir.py`
- Modify only if needed: `orchestrator/workflow_lisp/build.py`
- Modify only if needed: `orchestrator/workflow_lisp/source_map.py`
- Test when `orchestrator/workflow/executable_ir.py` changes: `tests/test_workflow_ir_lowering.py`
- Test when `orchestrator/workflow/runtime_plan.py` or `orchestrator/workflow/loaded_bundle.py` changes: `tests/test_workflow_state_projection.py`
- Test when `orchestrator/workflow_lisp/build.py` changes: `tests/test_workflow_lisp_build_artifacts.py`
- Test when `orchestrator/workflow_lisp/source_map.py` changes: `tests/test_workflow_lisp_source_map.py`

- [ ] **Step 1: Add failing bridge-integrity regressions**

Extend `tests/test_workflow_semantic_ir.py` with focused assertions that:

- the executable node set in all four surfaces matches exactly for one compiled frontend bundle:
  - `validated_bundle.ir.nodes`,
  - `validated_bundle.runtime_plan.nodes`,
  - `validated_bundle.semantic_ir.workflows[workflow_name].executable_bridge.node_ids`,
  - persisted source-map `executable_nodes[*].node_id`;
- serialized executable IR contains no compile-time-only callable/typecheck/source-map payloads;
- corrupting source-map executable coverage still fails with the current source-map diagnostic family, not `executable_ir_invalid`;
- corrupting semantic-IR executable bridges still fails with `semantic_ir_invalid`, not `executable_ir_invalid`.

- [ ] **Step 2: Run the semantic-IR selector**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_semantic_ir.py -q
python -m pytest tests/test_workflow_semantic_ir.py -q
```

Expected: failures, if any, should reveal remaining bridge mismatches or missing serializer/validation guards.

- [ ] **Step 3: Make only the minimal bridge adjustments required by tests**

Only if the failing tests prove it necessary:

- tighten `orchestrator/workflow/executable_ir.py` only if the semantic-IR bridge selector exposes a remaining executable-validator gap on node/reference integrity or compile-time-value erasure that belongs to the authoritative executable contract rather than to a derived projection;
- tighten `orchestrator/workflow/runtime_plan.py` to assume a schema-validated executable input and to reject any new inconsistent bridge state exposed by the executable validator;
- tighten `orchestrator/workflow/loaded_bundle.py` only if the failing bridge or executor-path tests prove the bundle surface needs a bounded alignment change so validated executable IR, derived `runtime_plan`, and exported bundle accessors stay coherent without introducing a second bundle type or alternate executable handle;
- tighten `orchestrator/workflow/semantic_ir.py` only if the failing bridge assertions prove the executable-bridge node-set or `semantic_ir_invalid` classification defect lives in semantic-IR derivation rather than in executable validation or source-map projection;
- tighten `orchestrator/workflow_lisp/build.py` only if the failing bridge selector proves serialized executable IR still leaks compile-time payloads or diverges from the canonical validated executable artifact bytes;
- tighten `orchestrator/workflow_lisp/source_map.py` so executable-node coverage is emitted only for validated node ids and continues to reject guessed lowered-step ids.

Do not move bridge authority away from executable IR.

- [ ] **Step 3a: Re-run the direct executable-contract selector if `executable_ir.py` changed**

Run when and only when Step 3 required edits to `orchestrator/workflow/executable_ir.py`:

```bash
python -m pytest --collect-only tests/test_workflow_ir_lowering.py -q
python -m pytest tests/test_workflow_ir_lowering.py -q
```

Expected: PASS, proving any bridge-driven validator adjustment still preserves the authoritative executable schema, serializer, and lowering-path validation checkpoint.

- [ ] **Step 4: Run the direct runtime-plan characterization selector if `runtime_plan.py` or `loaded_bundle.py` changed**

Run when and only when Step 3 required edits to `orchestrator/workflow/runtime_plan.py` or `orchestrator/workflow/loaded_bundle.py`:

```bash
python -m pytest --collect-only tests/test_workflow_state_projection.py -q
python -m pytest tests/test_workflow_state_projection.py -q
```

Expected: PASS, proving the executable-contract slice did not regress runtime-plan topology, dependency ordering, execution indexes, or finalization checkpoint behavior on the shared characterization surface that owns those guarantees.

- [ ] **Step 5: Run the direct source-map characterization selector if `source_map.py` changed**

Run when and only when Step 3 required edits to `orchestrator/workflow_lisp/source_map.py`:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_source_map.py -q
python -m pytest tests/test_workflow_lisp_source_map.py -q
```

Expected: PASS, proving the executable-contract slice did not regress authored-span mapping, generated executable-node coverage, or source-map projection invariants on the direct characterization surface that owns those guarantees.

- [ ] **Step 5a: Re-run the direct build-artifact selector if `build.py` changed**

Run when and only when Step 3 required edits to `orchestrator/workflow_lisp/build.py`:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_build_artifacts.py -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -q
```

Expected: PASS, proving any bridge-driven serialization fix still emits canonical `executable_ir.json` bytes and truthful manifest/export status without introducing a second rendering path.

- [ ] **Step 6: Run the full focused suite**

Run:

```bash
python -m pytest \
  tests/test_workflow_ir_lowering.py \
  tests/test_workflow_semantic_ir.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_diagnostics.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_cli.py -q
```

If Step 3 changed `orchestrator/workflow_lisp/source_map.py`, re-run the same command with `tests/test_workflow_lisp_source_map.py` appended before `-q` so the final focused suite includes the direct source-map characterization module alongside the cross-layer regression set.

Expected: PASS across executable schema validation, bridge integrity, shared-validation remap preservation, build artifacts, diagnostics, and public CLI export coverage. If `runtime_plan.py` or `loaded_bundle.py` changed, this suite complements the required direct runtime-plan characterization pass from Step 4 rather than replacing it. If `source_map.py` changed, this suite must include `tests/test_workflow_lisp_source_map.py` in addition to the required narrow selector from Step 5 rather than relying on indirect bridge coverage alone.

- [ ] **Step 7: Run the reusable-boundary compatibility selectors**

Run:

```bash
python -m pytest \
  tests/test_workflow_lisp_build_artifacts.py::test_build_accepts_compiled_imported_bundle_manifests \
  tests/test_workflow_lisp_phase_stdlib.py::test_resume_or_start_imported_workflow_call_uses_shared_managed_write_root_bundle_path \
  tests/test_workflow_lisp_procedures.py::test_lowering_preloads_nested_private_workflow_procedure_dependencies -q
```

Expected: PASS, proving imported compiled bundles and same-file Workflow Lisp bundles still cross reusable boundaries through validated bundle surfaces rather than executable-only sidecars.

- [ ] **Step 8: Run the executor-path integration selectors**

Run:

```bash
python -m pytest \
  tests/test_runtime_observability.py::test_executor_uses_bundle_runtime_plan_for_top_level_ordering \
  tests/test_workflow_executor_characterization.py::test_executor_uses_ir_raw_for_each_payloads_when_legacy_adapter_payload_is_missing -q
```

Expected: PASS, proving `WorkflowExecutor` still consumes the validated `LoadedWorkflowBundle` bridge correctly after the executable schema and validator changes: top-level ordering still comes from `bundle.runtime_plan`, and execution still reads executable-IR payloads from the validated bundle rather than from a stale projection or alternate authority path.

- [ ] **Step 9: Run one public `compile` CLI smoke check from the repo root**

Run:

```bash
python -m orchestrator compile tests/fixtures/workflow_lisp/valid/pointer_materialization_effects.orc \
  --entry-workflow orchestrate \
  --source-root tests/fixtures/workflow_lisp/valid \
  --provider-externs-file tests/fixtures/workflow_lisp/cli/providers.json \
  --prompt-externs-file tests/fixtures/workflow_lisp/cli/prompts.json \
  --command-boundaries-file tests/fixtures/workflow_lisp/cli/commands.json \
  --emit-executable-ir .orchestrate/tmp/executable-ir-smoke/executable_ir.json \
  --emit-runtime-plan .orchestrate/tmp/executable-ir-smoke/runtime_plan.json \
  --emit-semantic-ir .orchestrate/tmp/executable-ir-smoke/semantic_ir.json \
  --emit-source-map .orchestrate/tmp/executable-ir-smoke/source_map.json
```

Expected: PASS with a JSON summary from the supported CLI entrypoint, exported artifact paths for `executable_ir`, `runtime_plan`, `semantic_ir`, and `source_map`, and canonical emitted files at `.orchestrate/tmp/executable-ir-smoke/`.

- [ ] **Step 10: Run one public `explain` CLI smoke check from the repo root**

Run:

```bash
python -m orchestrator explain tests/fixtures/workflow_lisp/valid/pointer_materialization_effects.orc \
  --entry-workflow orchestrate \
  --source-root tests/fixtures/workflow_lisp/valid \
  --provider-externs-file tests/fixtures/workflow_lisp/cli/providers.json \
  --prompt-externs-file tests/fixtures/workflow_lisp/cli/prompts.json \
  --command-boundaries-file tests/fixtures/workflow_lisp/cli/commands.json \
  --emit-executable-ir .orchestrate/tmp/executable-ir-smoke/explain_executable_ir.json \
  --emit-runtime-plan .orchestrate/tmp/executable-ir-smoke/explain_runtime_plan.json \
  --emit-semantic-ir .orchestrate/tmp/executable-ir-smoke/explain_semantic_ir.json \
  --emit-source-map .orchestrate/tmp/executable-ir-smoke/explain_source_map.json
```

Expected: PASS with the supported `explain` CLI entrypoint exporting the same canonical artifact families as `compile`, proving the public `explain` parser/selection/export path accepts and emits `executable_ir` and `runtime_plan` as shipped.

- [ ] **Step 11: Commit the bounded slice**

Run:

```bash
git add \
  orchestrator/workflow/executable_ir.py \
  orchestrator/workflow/lowering.py \
  orchestrator/workflow_lisp/compiler.py \
  orchestrator/workflow_lisp/diagnostics.py \
  orchestrator/workflow_lisp/lowering.py \
  orchestrator/workflow_lisp/build.py \
  orchestrator/cli/main.py \
  orchestrator/cli/commands/compile.py \
  orchestrator/cli/commands/explain.py \
  tests/test_workflow_ir_lowering.py \
  tests/test_workflow_semantic_ir.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_diagnostics.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_cli.py
git add tests/test_workflow_state_projection.py
git add orchestrator/workflow/runtime_plan.py
git add orchestrator/workflow/loaded_bundle.py
git add orchestrator/workflow/semantic_ir.py
git add orchestrator/workflow_lisp/source_map.py
git commit -m "feat: formalize workflow executable ir contract"
```

Expected: one commit containing only the executable-IR component-contract slice. Run `git add tests/test_workflow_state_projection.py`, `git add orchestrator/workflow/runtime_plan.py`, and `git add orchestrator/workflow/loaded_bundle.py` only if Step 3 required the sanctioned runtime-plan/bundle path; run `git add orchestrator/workflow/semantic_ir.py` only if Step 3 required the sanctioned semantic-IR bridge path; and run `git add orchestrator/workflow_lisp/source_map.py` only if Step 3 required the sanctioned source-map path.

## Completion Criteria

The slice is complete only when all of the following are true:

- `ExecutableWorkflow` carries an explicit shared executable schema/version distinct from DSL versioning.
- Shared executable validation exists and runs before `runtime_plan` / `semantic_ir` derivation and again from the Workflow Lisp `executable` pass.
- Initial bundle-construction failures remain owned by `shared_validation`, while post-`shared_validation` executable-pass revalidation failures surface as `executable_ir_invalid` with authored Workflow Lisp remapping.
- `executable_ir.json` and `runtime_plan.json` are treated as canonical emitted artifacts in manifest/export behavior and in the supported `python -m orchestrator compile|explain` export API.
- Semantic IR, runtime plan, source map, and serialized executable IR all reference the same validated executable node universe.
- Imported compiled bundles and same-file Workflow Lisp bundles continue to cross reusable boundaries as validated `LoadedWorkflowBundle` values.
- The focused pytest suite, the reusable-boundary selectors, the executor-path integration selectors, and the public frontend CLI smoke commands all pass from the repo root.
