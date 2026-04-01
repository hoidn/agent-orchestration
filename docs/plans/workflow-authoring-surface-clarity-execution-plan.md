# Workflow Authoring Surface Clarity Execution Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Align the repo around one four-surface workflow-authoring vocabulary, migrate bundled reusable-workflow prompt assets onto the asset surface, and add only the narrow advisory lint needed to steer new boundary authoring without changing runtime semantics.

**Architecture:** Land the work in presentation-order, not implementation-order. First update the authoritative specs, entry docs, and authoring guide so they all describe the same four surfaces and the same version-accurate consume behavior. Next migrate repo-owned prompt files shipped with imported library workflows into the workflow-source tree and switch those callees to `asset_file` so reusable examples stop teaching workspace-root prompt staging. Then add high-confidence boundary compatibility coverage plus the v2.9 advisory lint for redundant workflow-boundary `kind: relpath`, and rewrite canonical workflow boundaries to the preferred `type: relpath` form before closing with targeted example/runtime verification.

**Tech Stack:** Markdown specs/docs, YAML workflows and prompt assets, Python loader/linting code, pytest unit/integration suites, orchestrator CLI dry-run smoke checks.

---

## Global Guardrails

- Keep this tranche docs/examples/lint only. Do not change provider runtime behavior, prompt composition order, workflow-boundary binding/export semantics, or consume/publish execution semantics.
- Treat the four-surface vocabulary as the source of truth everywhere it is restated:
  - workflow boundary: top-level `inputs`, `outputs`
  - runtime dependencies: `depends_on`, `consumes`
  - provider prompt sources: `input_file`, `asset_file`, `asset_depends_on`
  - artifact storage / lineage: top-level `artifacts`, `expected_outputs`, `output_bundle`, `publishes`
- Do not enable the new boundary lint while repo-owned canonical workflows still violate the preferred boundary form.
- Migrate bundled reusable prompt assets by moving the repo-owned prompt files into the reusable workflow source tree; do not leave duplicate canonical copies in both `prompts/workflows/...` and `workflows/library/...`.
- Keep `input_file` for workspace-owned or runtime-generated prompt material only. Do not add heuristic `input_file` misuse warnings in this tranche.
- Update active catalogs/indexes in the same pass as path migrations so docs do not point at stale prompt locations.
- Leave historical ADRs, archived plans, and unrelated examples alone unless they are part of the active canonical surface for this feature.

## Compatibility And Migration Boundary

- No `state.json` or run-root migration is expected.
- Existing workflows that declare top-level workflow-boundary `kind: relpath` plus `type: relpath` must continue to load and execute unchanged; the new behavior is advisory lint only.
- Top-level `artifacts`, step `expected_outputs`, and `output_bundle` keep their current `kind` semantics. The preferred omission of `kind` applies only to top-level workflow `inputs` and `outputs`.
- `input_file` remains fully supported and stays WORKSPACE-relative, including under `call`.
- `asset_file` and `asset_depends_on` remain provider-only, workflow-source-relative surfaces. This work only migrates repo-owned bundled assets for reusable imported workflows onto that existing surface.
- Prompt-asset migration is repo-internal/manual: update YAML references, tests, and catalogs together. No runtime fallback or automatic path rewrite is required.
- Consume wording must stay version-accurate:
  - `version: "1.2"` / `"1.3"` relpath consumes materialize the canonical pointer file
  - `version: "1.4"` relpath consumes are read-only at preflight
  - scalar consumes never write pointer files

## Explicit Non-Goals

- Renaming or removing `input_file` in this tranche.
- Changing prompt composition order, dependency injection order, or provider runtime delivery semantics.
- Changing workflow-boundary binding/export behavior or reclassifying prompt sources as workflow inputs.
- Changing `depends_on`, `consumes`, `publishes`, or artifact freshness semantics.
- Removing `kind` from the DSL outright or adding breaking loader validation for redundant boundary authoring.
- Rewriting historical docs solely to normalize wording.

### Tranche 1: Align Specs, Entry Docs, And Authoring Guidance

**Files:**
- Modify: `docs/index.md`
- Modify: `specs/index.md`
- Modify: `docs/runtime_execution_lifecycle.md`
- Modify: `docs/workflow_drafting_guide.md`
- Modify: `specs/dsl.md`
- Modify: `specs/providers.md`
- Modify: `specs/variables.md`
- Reference: `specs/dependencies.md`

**Work:**
- Replace the older reduced prompt model in entry-point docs with the approved four-surface vocabulary.
- Make `specs/dsl.md`, `specs/providers.md`, and `specs/variables.md` describe the same boundary split:
  - workflow `inputs` / `outputs` are interface contracts
  - `depends_on` / `consumes` are runtime dependencies
  - `input_file` / `asset_file` / `asset_depends_on` are provider prompt sources
  - `artifacts` / `expected_outputs` / `output_bundle` / `publishes` are storage or lineage surfaces
- Correct `docs/runtime_execution_lifecycle.md` and any other high-traffic summary text so they no longer imply provider prompts are just `input_file` plus dependency injection.
- Make consume wording version-accurate and identical across `specs/dsl.md` and `specs/variables.md`.
- Add authoring-guide guidance for when bundled reusable prompt assets belong on `asset_file` versus when runtime-owned prompt material should stay on `input_file`.

**Verification:**
```bash
rg -n "workflow boundary|runtime dependencies|provider prompt sources|artifact storage / lineage|input_file plus optional dependency injection|= input_file literal" \
  docs/index.md specs/index.md docs/runtime_execution_lifecycle.md docs/workflow_drafting_guide.md specs/dsl.md specs/providers.md specs/variables.md -S
pytest tests/test_artifact_dataflow_integration.py -k "v14_consume_relpath_is_read_only_for_pointer_file" -v
```

**Checkpoint:** Do not move prompt assets or add lint until the authoritative docs all describe the same four surfaces and the same consume-version boundary.

### Tranche 2: Migrate Bundled Reusable Prompt Assets Onto The Asset Surface

**Files:**
- Create: `workflows/library/prompts/design_plan_impl_stack_v2_call/draft_design.md`
- Create: `workflows/library/prompts/design_plan_impl_stack_v2_call/review_design.md`
- Create: `workflows/library/prompts/design_plan_impl_stack_v2_call/revise_design.md`
- Create: `workflows/library/prompts/design_plan_impl_stack_v2_call/draft_plan.md`
- Create: `workflows/library/prompts/design_plan_impl_stack_v2_call/review_plan.md`
- Create: `workflows/library/prompts/design_plan_impl_stack_v2_call/revise_plan.md`
- Create: `workflows/library/prompts/design_plan_impl_stack_v2_call/implement_plan.md`
- Create: `workflows/library/prompts/design_plan_impl_stack_v2_call/review_implementation.md`
- Create: `workflows/library/prompts/design_plan_impl_stack_v2_call/fix_implementation.md`
- Create: `workflows/library/prompts/dsl_follow_on_plan_impl_loop_v2_call/draft_plan.md`
- Create: `workflows/library/prompts/dsl_follow_on_plan_impl_loop_v2_call/review_plan.md`
- Create: `workflows/library/prompts/dsl_follow_on_plan_impl_loop_v2_call/revise_plan.md`
- Create: `workflows/library/prompts/dsl_follow_on_plan_impl_loop_v2_call/implement_plan.md`
- Create: `workflows/library/prompts/dsl_follow_on_plan_impl_loop_v2_call/review_implementation.md`
- Create: `workflows/library/prompts/dsl_follow_on_plan_impl_loop_v2_call/fix_implementation.md`
- Modify: `workflows/library/tracked_design_phase.yaml`
- Modify: `workflows/library/tracked_plan_phase.yaml`
- Modify: `workflows/library/design_plan_impl_implementation_phase.yaml`
- Modify: `workflows/library/follow_on_plan_phase.yaml`
- Modify: `workflows/library/follow_on_implementation_phase.yaml`
- Modify: `tests/test_workflow_examples_v0.py`
- Modify: `workflows/README.md`
- Modify: `prompts/README.md`
- Delete: `prompts/workflows/design_plan_impl_stack_v2_call/*` after active references are updated
- Delete: `prompts/workflows/dsl_follow_on_plan_impl_loop_v2_call/*` after active references are updated

**Work:**
- Move the repo-owned prompt families used by imported library workflows from `prompts/workflows/...` into `workflows/library/prompts/...`.
- Switch the affected imported workflows from workspace-root `input_file` paths to workflow-source-relative `asset_file` paths.
- Keep the migration narrow:
  - use `asset_file` for the base prompt files that ship with the callee
  - only introduce `asset_depends_on` if a migrated prompt family actually has bundled companion assets that belong in separate files
  - do not convert caller-supplied, generated, or workspace-owned prompt files
- Update `tests/test_workflow_examples_v0.py` so every affected example-runtime fixture copies the migrated library prompt assets from the workflow-source tree rather than from `prompts/workflows/...`, including the backlog-priority stack runtime alongside the direct design-stack and follow-on call runtimes.
- Update `workflows/README.md` and `prompts/README.md` so the catalog reflects the new self-contained reusable-workflow asset layout.

**Verification:**
```bash
rg -n "prompts/workflows/(design_plan_impl_stack_v2_call|dsl_follow_on_plan_impl_loop_v2_call)" \
  workflows tests/test_workflow_examples_v0.py workflows/README.md prompts/README.md -S
pytest tests/test_prompt_contract_injection.py -k "asset_file or asset_depends_on" -v
pytest tests/test_workflow_examples_v0.py -k "backlog_priority_design_plan_impl_stack_v2_call_runtime or dsl_follow_on_plan_impl_review_loop_v2_call_runtime or design_plan_impl_review_stack_v2_call_runtime" -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.yaml --dry-run
```

**Checkpoint:** Do not land boundary lint while imported reusable workflows or their active runtime fixtures, including the backlog-priority stack coverage, still depend on workspace-root prompt paths.

### Tranche 3: Add Boundary Compatibility Coverage, Enable Narrow Lint, And Rewrite Canonical Boundary Forms

**Files:**
- Modify: `orchestrator/workflow/linting.py`
- Modify: `tests/test_dsl_linting.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_workflow_output_contract_integration.py`
- Modify: `specs/versioning.md`
- Modify: `workflows/examples/design_plan_impl_review_stack_v2_call.yaml`
- Modify: `workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml`
- Modify: `workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml`
- Modify: `workflows/examples/workflow_signature_demo.yaml`
- Modify: `workflows/examples/library/repeat_until_review_loop.yaml`
- Modify: `workflows/library/review_fix_loop.yaml`
- Modify: `workflows/library/tracked_design_phase.yaml`
- Modify: `workflows/library/tracked_plan_phase.yaml`
- Modify: `workflows/library/design_plan_impl_implementation_phase.yaml`
- Modify: `workflows/library/follow_on_plan_phase.yaml`
- Modify: `workflows/library/follow_on_implementation_phase.yaml`
- Modify any other active `workflows/examples/` or `workflows/library/` file found by the repo-root audit that still uses redundant top-level boundary `kind: relpath`

**Work:**
- Add compatibility tests proving top-level workflow `inputs` and `outputs` still accept:
  - `type: relpath` without `kind`
  - explicit `kind: relpath` plus `type: relpath` for backward compatibility
- Add the v2.9 advisory lint rule only for top-level workflow-boundary `inputs` and `outputs` where `kind: relpath` and `type: relpath` appear together.
- Keep the lint rule scoped away from:
  - top-level `artifacts`
  - step `expected_outputs`
  - `output_bundle`
  - scalar workflow-boundary contracts
- Rewrite active canonical examples and reusable library workflows to omit redundant boundary `kind: relpath` while leaving artifact registries unchanged.
- Add the migration note to `specs/versioning.md` so the preferred style and advisory-warning boundary are documented in the normative version history.

**Verification:**
```bash
pytest --collect-only tests/test_loader_validation.py tests/test_dsl_linting.py tests/test_workflow_output_contract_integration.py -q
pytest tests/test_loader_validation.py tests/test_dsl_linting.py tests/test_workflow_output_contract_integration.py -k "workflow or boundary or relpath or lint" -v
pytest tests/test_workflow_examples_v0.py -k "workflow_signature or dsl_follow_on_plan_impl_review_loop_v2_call_runtime or design_plan_impl_review_stack_v2_call_runtime" -v
rg -n "kind: relpath" workflows/examples workflows/library -S
```

**Checkpoint:** The repo is ready for this tranche only when the new lint is passing, current canonical workflows no longer trigger it for top-level boundaries, and active examples still run.

### Tranche 4: Final Integration Sweep And Release-Quality Verification

**Files:**
- Modify only the files still showing active-surface drift after the tranche-level checks above

**Work:**
- Run one final active-surface audit for stale vocabulary, stale prompt paths, and redundant canonical boundary authoring using only the active files this tranche owns; exclude `docs/plans/`, archived docs, and other historical materials the plan explicitly leaves untouched.
- Re-run the targeted tests as one combined gate so docs, migrated reusable workflows, canonical examples, and lint behavior are all proven together.
- Re-run at least one orchestrator smoke from the repo root and record the exact command/output in the implementation report.
- Finish with `git diff --check` so path migrations and YAML/doc edits do not leave formatting damage behind.

**Verification:**
```bash
rg -n "input_file plus optional dependency injection|= input_file literal" \
  docs/index.md specs/index.md docs/runtime_execution_lifecycle.md docs/workflow_drafting_guide.md specs/dsl.md specs/providers.md specs/variables.md -S
rg -n "prompts/workflows/(design_plan_impl_stack_v2_call|dsl_follow_on_plan_impl_loop_v2_call)" \
  workflows tests/test_workflow_examples_v0.py workflows/README.md prompts/README.md -S
rg -n "kind: relpath" workflows/examples workflows/library -S
pytest tests/test_artifact_dataflow_integration.py -k "v14_consume_relpath_is_read_only_for_pointer_file" -v
pytest tests/test_prompt_contract_injection.py -k "asset_file or asset_depends_on" -v
pytest tests/test_loader_validation.py tests/test_dsl_linting.py tests/test_workflow_output_contract_integration.py tests/test_workflow_examples_v0.py -k "relpath or workflow_signature or backlog_priority_design_plan_impl_stack_v2_call or design_plan_impl_review_stack_v2_call or dsl_follow_on_plan_impl_review_loop_v2_call" -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.yaml --dry-run
git diff --check
```

**Checkpoint:** Do not mark the work complete until docs, examples, lint coverage, and the smoke command all agree on the same four-surface model and the same compatibility boundary.

## Final Integration Gate

Run this from the repo root after all tranches pass independently:

```bash
rg -n "input_file plus optional dependency injection|= input_file literal" \
  docs/index.md specs/index.md docs/runtime_execution_lifecycle.md docs/workflow_drafting_guide.md specs/dsl.md specs/providers.md specs/variables.md -S
rg -n "prompts/workflows/(design_plan_impl_stack_v2_call|dsl_follow_on_plan_impl_loop_v2_call)" \
  workflows tests/test_workflow_examples_v0.py workflows/README.md prompts/README.md -S
rg -n "kind: relpath" workflows/examples workflows/library -S
pytest tests/test_artifact_dataflow_integration.py -k "v14_consume_relpath_is_read_only_for_pointer_file" -v
pytest tests/test_prompt_contract_injection.py -k "asset_file or asset_depends_on" -v
pytest tests/test_loader_validation.py tests/test_dsl_linting.py tests/test_workflow_output_contract_integration.py tests/test_workflow_examples_v0.py -k "relpath or workflow_signature or backlog_priority_design_plan_impl_stack_v2_call or design_plan_impl_review_stack_v2_call or dsl_follow_on_plan_impl_review_loop_v2_call" -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.yaml --dry-run
git diff --check
```

Completion criteria:

- specs, entry docs, and the workflow drafting guide use the same four-surface vocabulary
- `specs/dsl.md` and `specs/variables.md` describe the same version-accurate consume materialization rules
- imported reusable workflows ship their bundled prompt assets from the workflow-source tree and no longer depend on workspace-root prompt paths
- active catalogs point at the migrated prompt locations
- top-level workflow boundaries prefer `type: relpath` alone while explicit `kind: relpath` remains backward-compatible
- v2.9 advisory lint warns only on redundant top-level workflow-boundary `kind: relpath`
- canonical repo workflows/examples no longer trigger the new lint for their own boundaries
