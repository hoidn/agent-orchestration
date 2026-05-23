# Executable IR And Runtime Plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the bounded executable-IR/runtime-plan contract so validated workflows carry one shared runtime-facing plan, compiled Workflow Lisp builds emit `runtime_plan.json`, and runtime indexing/observability no longer have to reconstruct the same topology ad hoc.

**Architecture:** Keep execution authority in `ExecutableWorkflow` and compatibility authority in `WorkflowStateProjection`. Add one shared derived `WorkflowRuntimePlan` in `orchestrator/workflow/`, thread it through `LoadedWorkflowBundle`, emit it as a compiled frontend artifact, and let the executor consume plan summaries only where they replace duplicated indexing logic. Do not fabricate Core AST or Semantic IR artifacts, and do not let the runtime plan become a second executor or a provenance-owning source-map substitute.

**Tech Stack:** Python dataclasses, `orchestrator/workflow`, `orchestrator/workflow_lisp`, existing loader/build/runtime surfaces, pytest, and the checked-in Workflow Lisp CLI fixtures.

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
  - `64. Snapshot Validation`
  - `74. Source Map Requirements`
  - `75. Runtime Observability`
  - `76. Build Artifacts`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `6. Lowering Contract`
  - `9. Source Spans And Diagnostics`
  - `10. Validation`
  - `14. Implementation Stages`
- `docs/design/workflow_lisp_semantic_workflow_ir.md`
- `docs/design/workflow_lisp_source_map.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/executable-ir-runtime-plan/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/2/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/2/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

## Current Repo Baseline

Assume this exact starting point:

- `docs/steering.md` is empty in this checkout and does not widen scope.
- `progress_ledger.json` currently has no events, so do not infer partial implementation from ledger state.
- `orchestrator/workflow/executable_ir.py` already defines the authoritative shared runtime node/config dataclasses.
- `orchestrator/workflow/state_projection.py` already defines the compatibility projection, ordered top-level execution mapping, loop runtime-step-id rules, and call-boundary checkpoint helpers.
- `orchestrator/workflow/lowering.py` already lowers validated surface workflows to `(ExecutableWorkflow, WorkflowStateProjection)`.
- `orchestrator/workflow/loaded_bundle.py` already transports `surface`, `ir`, `projection`, `imports`, and `provenance`, but no runtime-plan surface yet.
- `orchestrator/loader.py` and `orchestrator/workflow_lisp/lowering.py` both construct `LoadedWorkflowBundle` instances directly after shared lowering.
- `orchestrator/workflow/executor.py` currently rebuilds ordered node ids and related indexing from `ir` and `projection`.
- `orchestrator/workflow_lisp/build.py` already emits `executable_ir.json`, `source_map.json`, and `workflow_boundary_projection.json`, but not `runtime_plan.json`.
- `orchestrator/workflow_lisp/source_map.py` already persists executable-node lineage keyed by runtime-visible node ids. Preserve that alignment.
- `FrontendBuildManifest.artifact_status` already keeps `core_workflow_ast` and `semantic_ir` marked as `deferred_shared_contract`. Preserve that honesty rule.

## Hard Scope Limits

Implement only the selected `executable-ir-runtime-plan` slice:

- one shared `WorkflowRuntimePlan` derived from `ExecutableWorkflow + WorkflowStateProjection`;
- one deterministic serialized `runtime_plan.json` build artifact for compiled `.orc` entrypoints;
- bundle/runtime transport of runtime-plan data for YAML and Lisp workflows alike;
- plan summaries for ordering, dependencies, artifacts, snapshots, observability hooks, and resume checkpoints;
- narrow executor adoption where runtime-plan summaries replace duplicated indexing logic;
- focused lowering, projection, resume, observability, and build-artifact verification.

Explicit non-goals:

- no new frontend language semantics, stdlib forms, parsing/module/macro/procedure work, or workflow-ref redesign;
- no provider/queue/state-storage redesign and no second execution path;
- no fabricated `core_workflow_ast.json` or `semantic_ir.json`;
- no shell-text inspection, report parsing, or hidden command semantics;
- no provenance duplication of `source_map.json` into the runtime plan.

## Non-Negotiable Contracts

Keep these contracts fixed during execution:

- `ExecutableWorkflow` remains the only execution authority.
- `WorkflowStateProjection` remains the compatibility and resume authority.
- `WorkflowRuntimePlan` is a derived indexed view, not a second mutable executor shape.
- `runtime_plan.json` must be versioned, serializable, and shared-runtime-owned. Use a dedicated schema constant such as `workflow_runtime_plan.v1`.
- Runtime-plan node summaries reference executable node ids and projection keys; they do not embed full step configs or authored source spans.
- Top-level order comes from `WorkflowStateProjection.ordered_execution_node_ids()`.
- Nested nodes stay represented through node summaries plus `nested_body_node_ids`; do not invent a fake global execution order for loop bodies.
- Artifact and snapshot summaries derive only from executable config surfaces:
  `publishes`,
  `expected_outputs`,
  `output_bundle`,
  `variant_output`,
  `pre_snapshot`,
  `select_variant_output`,
  and `materialize_artifacts`.
- Command metadata in the runtime plan comes only from declared command-boundary identity and kind. Do not inspect command text.
- Source provenance remains in `source_map.json`; the runtime plan may carry only the boolean/runtime-facing facts needed to join against that sidecar later.

## File Ownership

Create:

- `orchestrator/workflow/runtime_plan.py`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/executable-ir-runtime-plan/execution_plan.md` (this file)

Modify:

- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/workflow/executor.py`
- `orchestrator/loader.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/build.py`
- `tests/test_workflow_ir_lowering.py`
- `tests/test_workflow_state_projection.py`
- `tests/test_resume_command.py`
- `tests/test_runtime_observability.py`
- `tests/test_workflow_lisp_build_artifacts.py`

Modify only if a focused failing test proves the helper is required:

- `orchestrator/workflow/state_projection.py`
- `orchestrator/workflow_lisp/source_map.py`
- `tests/workflow_bundle_helpers.py`

Do not widen ownership into reader/typechecker/stdlib code. This slice is shared runtime-plan plumbing, not new language surface.

## Required Runtime-Plan Shape

Implement these shared records in `orchestrator/workflow/runtime_plan.py`:

- `WorkflowRuntimePlan`
  - `schema_version`
  - `workflow_name`
  - `ordered_node_ids`
  - `nodes`
  - `artifacts`
  - `snapshots`
  - `resume_checkpoints`
  - `observability`
- `RuntimePlanNode`
  - `node_id`
  - `step_id`
  - `presentation_key`
  - `display_name`
  - `kind`
  - `region`
  - `execution_index`
  - `lexical_scope`
  - `fallthrough_node_id`
  - `routed_transfer_targets`
  - `dependency_node_ids`
  - `nested_body_node_ids`
  - `call_alias`
  - `command_boundary_kind`
  - `command_boundary_name`
- `RuntimeArtifactPlan`
  - stable artifact/bundle key
  - source node id
  - contract name
  - contract kind
  - publication mode: `publishes`, `expected_output`, `output_bundle`, or `variant_output`
- `RuntimeSnapshotPlan`
  - owner node id
  - snapshot operation kind
  - related selector/candidate surface when present
  - `selection_relevant` boolean
- `RuntimeResumeCheckpoint`
  - checkpoint kind: `top_level_node`, `call_boundary`, `repeat_until_frame`, `for_each_frame`, or `finalization_node`
  - node id
  - step id
  - presentation key
  - runtime-step-id mode: `static` or `qualified_iteration`
  - iteration owner/suffix fields when the projection requires qualification
- `RuntimeObservabilityPlan`
  - workflow name
  - top-level ordered node ids
  - `has_compiled_frontend_lineage`
  - per-node display/presentation metadata
  - runtime-visible command-boundary summaries

Use `execution_index: int | None` for nested non-top-level nodes so the schema stays honest about the lack of a projection-owned global nested order.

## Task 1: Lock The Shared Runtime-Plan Contract With Failing Tests

**Files:**

- Create: `orchestrator/workflow/runtime_plan.py`
- Modify: `orchestrator/workflow/loaded_bundle.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `tests/test_workflow_ir_lowering.py`

- [ ] **Step 1: Add failing lowering tests for bundle-carried runtime plans**

Extend `tests/test_workflow_ir_lowering.py` so the loaded bundle must expose `runtime_plan` and the plan must satisfy these invariants:

- `runtime_plan.schema_version == "workflow_runtime_plan.v1"`;
- `runtime_plan.workflow_name == bundle.surface.name`;
- `runtime_plan.ordered_node_ids == bundle.projection.ordered_execution_node_ids()`;
- `runtime_plan.nodes` contains every executable node id in `bundle.ir.nodes`;
- top-level nodes have combined execution indexes matching body/finalization order, while nested loop-body nodes report `execution_index is None`;
- call boundaries surface `call_alias`;
- command nodes surface declared boundary kind/name when available;
- the legacy bundle still does not expose any raw/legacy workflow projection adapter.

- [ ] **Step 2: Run collection and the narrow lowering selector first**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_ir_lowering.py tests/test_workflow_state_projection.py tests/test_resume_command.py tests/test_runtime_observability.py tests/test_workflow_lisp_build_artifacts.py -q
python -m pytest tests/test_workflow_ir_lowering.py -q
```

Expected: collection succeeds, then the lowering module test fails because no runtime-plan contract or bundle field exists yet.

- [ ] **Step 3: Implement the shared runtime-plan module**

In `orchestrator/workflow/runtime_plan.py`, add:

- the schema/version constant and frozen dataclasses listed above;
- `derive_workflow_runtime_plan(ir, projection) -> WorkflowRuntimePlan`;
- `validate_workflow_runtime_plan(plan, ir, projection)` enforcing:
  - `ordered_node_ids` exactly match projection order;
  - every referenced node id exists in `ir.nodes`;
  - dependency targets, nested body ids, artifact source nodes, and checkpoint nodes all resolve;
  - each checkpoint tuple is unique by `(kind, node_id, step_id, runtime-step-id mode)`;
  - finalization nodes appear only after body nodes in `ordered_node_ids`.

Derive node summaries from the existing executable-node dataclasses instead of thawed compatibility dicts. Keep the module runtime-owned and free of frontend-only imports.

- [ ] **Step 4: Thread runtime-plan derivation into bundle construction**

Update the shared bundle construction path so both YAML and Workflow Lisp validated bundles carry runtime plans:

- add `runtime_plan` to `LoadedWorkflowBundle`;
- add a typed accessor helper in `loaded_bundle.py` if executor/runtime code benefits from it;
- derive the plan immediately after `lower_surface_workflow(surface)` in `orchestrator/loader.py` and `orchestrator/workflow_lisp/lowering.py`;
- keep `orchestrator/workflow/lowering.py` as the shared seam for executable lowering logic and avoid duplicating derivation rules in frontend code.

Do not change the execution authority: the bundle still carries `ir` and `projection`, with `runtime_plan` as a read-only derivative.

- [ ] **Step 5: Re-run the lowering selector and require a pass**

Run:

```bash
python -m pytest tests/test_workflow_ir_lowering.py -q
```

Expected: PASS with bundle-level runtime-plan coverage and no fabricated semantic artifacts.

## Task 2: Encode Dependencies, Artifacts, Snapshots, And Resume Checkpoints

**Files:**

- Modify: `orchestrator/workflow/runtime_plan.py`
- Modify: `orchestrator/workflow/state_projection.py` only if read-only helpers are needed
- Modify: `tests/test_workflow_state_projection.py`
- Modify: `tests/test_resume_command.py`

- [ ] **Step 1: Add failing topology/checkpoint tests**

Extend `tests/test_workflow_state_projection.py` and `tests/test_resume_command.py` to lock these behaviors:

- runtime-plan dependencies are derived from stable execution structure, not prompt text or thawed report content;
- `repeat_until` and `for_each` frame nodes expose `nested_body_node_ids` and checkpoint summaries aligned with the projection’s iteration runtime-step-id rules;
- call-boundary checkpoints preserve `iteration_owner_node_id` and runtime step-id suffix metadata for loop-qualified calls;
- finalization nodes appear as `finalization_node` checkpoints with body-count-offset execution indexes;
- artifact publication summaries and snapshot summaries come only from executable config fields;
- resume-related tests continue to use `WorkflowStateProjection` as the authority for actual restart decisions.

- [ ] **Step 2: Run the focused projection/resume selectors and confirm the failures are about missing runtime-plan coverage**

Run:

```bash
python -m pytest tests/test_workflow_state_projection.py -q
python -m pytest tests/test_resume_command.py -k 'projection or repeat_until or for_each' -q
```

Expected: FAIL on missing runtime-plan dependency/checkpoint summaries while existing projection-based restart behavior remains unchanged.

- [ ] **Step 3: Implement deterministic derivation rules**

In `derive_workflow_runtime_plan(...)`, compute:

- `ordered_node_ids` from `projection.ordered_execution_node_ids()`;
- incoming `dependency_node_ids` from:
  - immediate predecessor in top-level order for top-level nodes;
  - explicit `fallthrough_node_id` sources;
  - explicit routed-transfer sources;
  - container-to-body-entry relationships for loop frames;
  - nested-body predecessor chains inside `ForEachNode` and `RepeatUntilFrameNode`;
  - parent frame dependencies for nested call boundaries;
- `artifacts` by walking `StepCommonConfig` publication fields and preserving the publication mode separately instead of flattening everything into one artifact shape;
- `snapshots` by inspecting `pre_snapshot`, `select_variant_output`, and `materialize_artifacts` configuration only;
- `resume_checkpoints` from top-level projection entries, loop projections, and call-boundary projections without changing the projection’s actual restart API.

If a tiny read-only helper in `state_projection.py` makes checkpoint derivation clearer, add it there rather than duplicating projection-normalization logic in tests or the executor.

- [ ] **Step 4: Re-run the projection/resume selectors and require passes**

Run:

```bash
python -m pytest tests/test_workflow_state_projection.py -q
python -m pytest tests/test_resume_command.py -k 'projection or repeat_until or for_each' -q
```

Expected: PASS, with runtime-plan checkpoint metadata aligned to projection rules and no behavioral change to actual resume planning.

## Task 3: Emit `runtime_plan.json` And Lock Lineage/Manifest Alignment

**Files:**

- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `orchestrator/workflow_lisp/source_map.py` only if a focused test proves lineage normalization is missing
- Modify: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] **Step 1: Add failing build-artifact tests**

Extend `tests/test_workflow_lisp_build_artifacts.py` so compiled Workflow Lisp builds must:

- emit `runtime_plan.json`;
- include `runtime_plan` in `result.artifact_paths` and manifest artifact-path records;
- serialize the plan with `schema_version == "workflow_runtime_plan.v1"`;
- keep `core_workflow_ast` and `semantic_ir` as deferred shared contracts instead of silently replacing them with runtime-plan claims;
- prove runtime-plan node ids match the `source_map.json` executable-node lineage for the selected workflow;
- prove manifest/source-map coverage assertions still pass unchanged for the existing deferred surfaces.

- [ ] **Step 2: Run the focused build-artifact selector first**

Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k 'executable_ir or source_map or manifest' -q
```

Expected: FAIL because the build currently emits no runtime-plan artifact and the manifest has no path entry for it.

- [ ] **Step 3: Emit the new artifact without widening provenance scope**

Update `orchestrator/workflow_lisp/build.py` so:

- the validated bundle reconstruction preserves `runtime_plan`;
- `_write_build_artifacts(...)` writes `runtime_plan.json` using the bundle-carried plan;
- `_build_manifest(...)` includes the runtime-plan artifact path but does not treat it as a replacement for deferred Core AST or Semantic IR status;
- the serialized runtime plan stays source-map-adjacent and provenance-light: no duplicate authored spans, no copied expansion stacks, no absolute source-trace internals.

Only touch `orchestrator/workflow_lisp/source_map.py` if a failing lineage test shows executable-node ids need normalization to match the new runtime-plan node map.

- [ ] **Step 4: Re-run the build-artifact selector and require a pass**

Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k 'executable_ir or source_map or manifest' -q
```

Expected: PASS with `runtime_plan.json` emitted beside `executable_ir.json` and `source_map.json`.

## Task 4: Adopt Runtime-Plan Summaries In The Executor Without Replacing Projection Authority

**Files:**

- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_runtime_observability.py`

- [ ] **Step 1: Add failing executor/observability tests**

Extend `tests/test_runtime_observability.py` so the executor proves:

- ordered top-level node traversal can come from `bundle.runtime_plan.ordered_node_ids`;
- per-node display/presentation metadata remains stable when runtime-plan summaries are present;
- command-boundary display hints remain surfaced without parsing command text;
- compiled frontend source context still prefers executable-node lineage from `source_map.json`, with the runtime plan used only as the runtime-facing index.

- [ ] **Step 2: Run the observability selector first**

Run:

```bash
python -m pytest tests/test_runtime_observability.py -q
```

Expected: FAIL on new runtime-plan-aware assertions while the existing compiled-frontend source-map behavior remains intact.

- [ ] **Step 3: Switch duplicated runtime indexes to bundle-provided summaries**

In `orchestrator/workflow/executor.py`:

- cache `self.runtime_plan = self.loaded_bundle.runtime_plan`;
- use `runtime_plan.ordered_node_ids` for top-level ordered-node lookup where the executor currently rebuilds the same list from `ir.body_region`, `ir.finalization_region`, or projection ordering;
- use runtime-plan node summaries for display-name/presentation-key lookups and command-boundary hints when available;
- keep resume decisions, persisted-state compatibility checks, and current-step integrity anchored to `WorkflowStateProjection` and `ResumePlanner`.

Do not remove the existing projection fallback paths. YAML and partially constructed test bundles should still behave sensibly when only the shared bundle contract is present.

- [ ] **Step 4: Re-run the observability selector and require a pass**

Run:

```bash
python -m pytest tests/test_runtime_observability.py -q
```

Expected: PASS with runtime-plan-backed indexing and unchanged compiled-frontend provenance behavior.

## Task 5: Run The Required Verification And Smoke Commands

**Files:**

- No additional file edits.

- [ ] **Step 1: Re-run the focused shared-runtime selectors from the checked-in verification bundle**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_ir_lowering.py tests/test_workflow_state_projection.py tests/test_resume_command.py tests/test_runtime_observability.py tests/test_workflow_lisp_build_artifacts.py -q
python -m pytest tests/test_workflow_ir_lowering.py tests/test_workflow_state_projection.py -q
python -m pytest tests/test_resume_command.py -k 'projection or repeat_until or for_each' -q
python -m pytest tests/test_runtime_observability.py -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k 'executable_ir or source_map or manifest' -q
```

Expected: PASS across the focused lowering, projection, resume, observability, and build-artifact surfaces touched by this slice.

- [ ] **Step 2: Run the compile smoke command and verify `runtime_plan.json` is emitted**

Run:

```bash
python -m orchestrator compile tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix/neurips/entry.orc --entry-workflow orchestrate --source-root tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix --provider-externs-file tests/fixtures/workflow_lisp/cli/providers.json --prompt-externs-file tests/fixtures/workflow_lisp/cli/prompts.json --imported-workflow-bundles-file tests/fixtures/workflow_lisp/cli/imported_workflow_bundles.json --command-boundaries-file tests/fixtures/workflow_lisp/cli/commands.json
```

Expected: successful compile output under `.orchestrate/build/<fingerprint>/` containing `runtime_plan.json`, `executable_ir.json`, `source_map.json`, `workflow_boundary_projection.json`, and `manifest.json`.

- [ ] **Step 3: Run the dry-run smoke command against the live executor path**

Run:

```bash
python -m orchestrator run tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix/neurips/entry.orc --entry-workflow orchestrate --source-root tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix --provider-externs-file tests/fixtures/workflow_lisp/cli/providers.json --prompt-externs-file tests/fixtures/workflow_lisp/cli/prompts.json --imported-workflow-bundles-file tests/fixtures/workflow_lisp/cli/imported_workflow_bundles.json --command-boundaries-file tests/fixtures/workflow_lisp/cli/commands.json --input input__status=ready --input input__report=artifacts/work/existing-report.md --input report_path=artifacts/work/existing-report.md --dry-run
```

Expected: PASS without executor/runtime-plan mismatches, proving the new bundle surface stays aligned with the actual run path rather than only artifact serialization.

## Acceptance Conditions

The work is complete only when all of the following are true:

- there is one shared `WorkflowRuntimePlan` contract under `orchestrator/workflow/`;
- validated bundles for YAML and Workflow Lisp both carry `runtime_plan`;
- compiled Workflow Lisp builds emit `runtime_plan.json`;
- runtime-plan node ids align with `source_map.json` executable-node lineage;
- runtime-plan checkpoints align with projection-owned runtime-step-id rules;
- executor indexing can consume runtime-plan summaries without replacing projection-based resume authority;
- no Core AST or Semantic IR artifacts are fabricated or implied by the new runtime-plan surface.
