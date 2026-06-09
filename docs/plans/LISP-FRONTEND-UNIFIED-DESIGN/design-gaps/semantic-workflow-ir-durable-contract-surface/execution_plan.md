# Semantic Workflow IR Durable Contract Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining `semantic-workflow-ir-durable-contract-surface` gap by promoting the existing Semantic IR design note into a durable current-checkout component contract and adding one docs-index discoverability entry, without changing shared lowering, executable authority, or runtime behavior.

**Architecture:** Treat this as a docs-first, docs-mostly promotion over an already-landed shared Semantic IR implementation. `SemanticWorkflowIR` and `LoadedWorkflowBundle.semantic_ir` remain the durable typed semantic contract surface derived during shared bundle assembly, while validated executable IR remains executable authority and `runtime_plan`, build artifacts, debug YAML, and other reports remain derived views. Only touch Python or tests if a focused audit proves the promoted documentation would otherwise be false for the current checkout.

**Tech Stack:** Markdown docs under `docs/design/` and `docs/`, shared workflow/runtime Python modules as evidence sources, repo-root `rg` and `sed` verification commands, and narrow `pytest` selectors only if a truth-preserving corrective code change becomes necessary.

---

## Fixed Inputs

Treat these as authority for scope, wording, and verification boundaries:

- `docs/design/workflow_lisp_unified_frontend_design.md`
  - `36. Semantic Workflow IR Contract`
  - `37. Executable IR Contract`
  - `43. Source Map Contract`
  - `46. Acceptance Gate for Component Architecture`
  - `73. Recommended Sequence`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `0. Prerequisites, Boundaries, And Missing Internal Specs`
  - `47. Semantic IR`
  - `48. Executable IR`
  - `59. Validation Sequence`
  - `74. Source Map Requirements`
  - `76. Build Artifacts`
- `docs/design/workflow_lisp_semantic_workflow_ir.md`
- `docs/design/workflow_lisp_executable_ir.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/index.md`
- `docs/steering.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/work_instructions.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/semantic-workflow-ir-durable-contract-surface/implementation_architecture.md`
- `state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/6/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/6/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-UNIFIED-DESIGN/progress_ledger.json`

Treat these as implementation evidence that the promoted doc must match:

- `orchestrator/workflow/semantic_ir.py`
- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/workflow/runtime_plan.py`
- `orchestrator/workflow/executable_ir.py`
- `orchestrator/workflow_lisp/build.py`
- `tests/test_workflow_semantic_ir.py`
- `tests/test_workflow_lisp_build_artifacts.py`

## Current Repo Baseline

Assume this exact starting point unless the initial audit disproves it:

- `progress_ledger.json` has no events, so there is no later ledger evidence overriding the current code/tests.
- `docs/steering.md` is empty, so it does not widen this slice.
- `docs/design/workflow_lisp_semantic_workflow_ir.md` already exists, but it is still marked `Status: draft internal design` and is too thin to serve as the durable current-checkout contract.
- `docs/index.md` currently has no dedicated entry for `design/workflow_lisp_semantic_workflow_ir.md`.
- `docs/design/workflow_lisp_frontend_specification.md` already links the Semantic IR document in its internal component-contract list, so this slice does not need a new umbrella-spec pointer.
- `orchestrator/workflow/semantic_ir.py` already defines:
  - `WORKFLOW_SEMANTIC_IR_SCHEMA_VERSION = "workflow_semantic_ir.v1"`
  - `SemanticExecutableBridge`
  - `SemanticStatement`
  - `SemanticTypeEntry`
  - `SemanticContractEntry`
  - `SemanticRefEntry`
  - `SemanticEffectEntry`
  - `SemanticProofEntry`
  - `SemanticStateLayoutEntry`
  - `SemanticSourceMapBridgeEntry`
  - `SemanticCallEdge`
  - `SemanticPromptSurface`
  - `SemanticCommandBoundary`
  - `SemanticWorkflow`
  - `SemanticWorkflowIR`
  - `derive_workflow_semantic_ir(...)`
  - `validate_workflow_semantic_ir(...)`
  - `workflow_semantic_ir_to_json(...)`
- `orchestrator/workflow/loaded_bundle.py` already exposes `LoadedWorkflowBundle.semantic_ir` and `workflow_semantic_ir(...)`.
- `orchestrator/workflow/lowering.py` already validates executable IR, derives `runtime_plan`, derives Semantic IR, and returns a typed `LoadedWorkflowBundle`.
- `orchestrator/workflow_lisp/build.py` already emits `semantic_ir.json` and records it in the build manifest.
- `tests/test_workflow_semantic_ir.py` already proves catalog population, state-layout/source-map bridges, executable bridge coverage, command-boundary classification, prompt-surface/call-edge cataloging, promoted generated/adapted effects, and `semantic_ir_invalid` rejection behavior.
- `tests/test_workflow_lisp_build_artifacts.py` already proves `semantic_ir.json` emission, filename/status coverage, schema version locking, and source-map bridge lineage in build outputs.
- The missing gap is durable documentation surface and discoverability, not missing shared Semantic IR implementation.

## Success Criteria

The work is complete only when all of the following are true:

- `docs/design/workflow_lisp_semantic_workflow_ir.md` is rewritten as the durable repo-level Semantic IR component contract for the current checkout.
- The promoted doc explicitly states that Semantic IR is the typed semantic contract surface, not executable authority and not runtime execution ownership.
- The promoted doc explicitly preserves the boundary with:
  - `ExecutableWorkflow` / `LoadedWorkflowBundle.ir` as executable authority;
  - `runtime_plan` as a derived runtime-facing summary;
  - source maps as traceability artifacts;
  - `docs/design/workflow_command_adapter_contract.md` as the command-boundary authority source.
- The promoted doc names the current code-level anchors:
  - `WORKFLOW_SEMANTIC_IR_SCHEMA_VERSION`
  - `SemanticWorkflowIR`
  - `SemanticWorkflow`
  - `derive_workflow_semantic_ir(...)`
  - `validate_workflow_semantic_ir(...)`
  - `workflow_semantic_ir_to_json(...)`
  - `LoadedWorkflowBundle.semantic_ir`
  - `workflow_semantic_ir(...)`
- `docs/index.md` gains one discoverability entry for the Semantic IR contract adjacent to the other Workflow Lisp contract docs.
- No parent-spec rewrite, new runtime semantics, new Semantic IR schema entries, new validators, or unrelated backlog/doc churn is introduced.

## Scope Guardrails

Implement only the selected durable-contract-surface slice:

- promote the existing Semantic IR doc in place at `docs/design/workflow_lisp_semantic_workflow_ir.md`;
- add one narrow `docs/index.md` discoverability entry;
- keep all shared Python and tests as evidence-only surfaces unless a focused audit proves the new doc would otherwise be false.

Explicit non-goals:

- new Semantic IR schema fields, serializers, or validator behavior;
- new executable node kinds, runtime closures, dynamic dispatch, or runtime-native effects;
- direct frontend-to-Semantic-IR lowering that bypasses the shared bundle path;
- command-adapter redesign, report/pointer authority changes, or inline-command reinterpretation;
- frontend-spec rewrites beyond any truly minimal typo/consistency fix proven necessary during audit;
- progress-ledger edits, queue/backlog churn, helper scripts, or unrelated documentation cleanup.

## File Map

**Modify**

- `docs/design/workflow_lisp_semantic_workflow_ir.md`
- `docs/index.md`

**Evidence-only by default**

- `docs/design/workflow_lisp_executable_ir.md`
- `orchestrator/workflow/semantic_ir.py`
- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/workflow/runtime_plan.py`
- `orchestrator/workflow/executable_ir.py`
- `orchestrator/workflow_lisp/build.py`
- `tests/test_workflow_semantic_ir.py`
- `tests/test_workflow_lisp_build_artifacts.py`

## Required Content For The Promoted Semantic IR Doc

Rewrite `docs/design/workflow_lisp_semantic_workflow_ir.md` with these sections in this order:

1. `# Workflow Lisp Semantic Workflow IR`
2. `Status` and `Scope` lines that make the document current-checkout and component-contract oriented rather than aspirational.
3. `## Purpose`
4. `## Authority Boundary`
5. `## Relationship To Adjacent Layers`
6. `## Current Semantic Surface`
7. `## Validation Ownership`
8. `## Executable And Runtime-Plan Linkage`
9. `## Command Boundary Constraints`
10. `## Compile-Time Erasure And Source-Map Bridges`
11. `## Build Artifacts And Evidence`
12. `## Out Of Scope`

The content must name the current code-level anchors directly:

- `WORKFLOW_SEMANTIC_IR_SCHEMA_VERSION`
- `SemanticWorkflowIR`
- `SemanticWorkflow`
- `SemanticStatement`
- `SemanticTypeEntry`
- `SemanticContractEntry`
- `SemanticRefEntry`
- `SemanticEffectEntry`
- `SemanticProofEntry`
- `SemanticStateLayoutEntry`
- `SemanticSourceMapBridgeEntry`
- `SemanticCallEdge`
- `SemanticPromptSurface`
- `SemanticCommandBoundary`
- `SemanticExecutableBridge`
- `derive_workflow_semantic_ir(...)`
- `validate_workflow_semantic_ir(...)`
- `workflow_semantic_ir_to_json(...)`
- `LoadedWorkflowBundle.semantic_ir`
- `workflow_semantic_ir(...)`

The content must also state all of the following explicitly:

- Semantic IR is the durable typed semantic contract surface for the current checkout, but validated executable IR remains executable authority.
- Semantic IR is derived from the shared bundle path and must not be reconstructed from reports, debug YAML, pointer files, shell text, or prose summaries.
- `runtime_plan`, build summaries, dashboards, and debug YAML are derived views and do not redefine semantic authority.
- command/provider semantics remain governed by `docs/design/workflow_command_adapter_contract.md`, not by reinterpreting shell text or adapter payloads.
- compile-time-only values such as unresolved `ProcRef`, `let-proc` metadata, syntax objects, macro-expansion leftovers, and runtime-closure markers must not survive into semantic/runtime artifacts.
- source-map bridges must preserve traceability from semantic entries back to authored or generated subjects.
- future schema, validator, or runtime-surface changes require a separate reviewed contract and must not be implied by this promotion pass.

## Exact Discoverability Edits

Apply only these narrow discoverability edits:

- In `docs/index.md`, add one Workflow Lisp design entry for `design/workflow_lisp_semantic_workflow_ir.md` adjacent to the other Workflow Lisp component-contract pages, ideally beside the existing Executable IR entry.
- Do not add a new parent-spec pointer unless the audit proves the existing `docs/design/workflow_lisp_frontend_specification.md` link is missing or wrong.
- Keep surrounding index edits minimal: one new entry, concise description, concise keyword line, concise "Use this when" line.

## Task 1: Audit The Current Checkout Facts Before Editing

**Files:**

- No edits yet

- [ ] Confirm the current code and test anchors from the repo root:

```bash
rg -n "WORKFLOW_SEMANTIC_IR_SCHEMA_VERSION|class SemanticWorkflowIR|class SemanticWorkflow\\b|class SemanticStatement\\b|class SemanticTypeEntry\\b|class SemanticContractEntry\\b|class SemanticRefEntry\\b|class SemanticEffectEntry\\b|class SemanticProofEntry\\b|class SemanticStateLayoutEntry\\b|class SemanticSourceMapBridgeEntry\\b|class SemanticCallEdge\\b|class SemanticPromptSurface\\b|class SemanticCommandBoundary\\b|class SemanticExecutableBridge\\b|derive_workflow_semantic_ir|validate_workflow_semantic_ir|workflow_semantic_ir_to_json" orchestrator/workflow/semantic_ir.py
rg -n "semantic_ir|workflow_semantic_ir\\(" orchestrator/workflow/loaded_bundle.py orchestrator/workflow/lowering.py orchestrator/workflow_lisp/build.py
rg -n "semantic_ir_invalid|semantic_ir\\.json|workflow_semantic_ir|Semantic IR" tests/test_workflow_semantic_ir.py tests/test_workflow_lisp_build_artifacts.py
```

- [ ] Re-read the architecture/work-item constraints immediately before drafting:

```bash
sed -n '1,260p' docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/semantic-workflow-ir-durable-contract-surface/implementation_architecture.md
sed -n '1,260p' state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/6/design-gap-architect/work_item_context.md
```

- [ ] If the audit contradicts any baseline claim above, record the contradiction in the implementation handoff before editing docs. Do not silently widen scope.

## Task 2: Promote The Semantic IR Doc To A Durable Current-Checkout Contract

**Files:**

- Modify: `docs/design/workflow_lisp_semantic_workflow_ir.md`

- [ ] Rewrite the document using the required section order above.
- [ ] Replace draft/aspirational wording with current-checkout contract language anchored in the real shared implementation.
- [ ] Describe the typed semantic inventory in repo terms rather than as a future wish list.
- [ ] Preserve the boundary that executable IR is executable authority and Semantic IR is the typed semantic projection/contract surface.
- [ ] Reference `docs/design/workflow_command_adapter_contract.md` instead of restating command semantics as a competing authority source.
- [ ] Keep the document bounded to the current Semantic IR layer. Do not redesign Core AST, Executable IR, runtime plan, or runtime execution here.

**Blocking verification after Task 2:**

- [ ] Run:

```bash
rg -n "^# Workflow Lisp Semantic Workflow IR$|^Status: |^Scope: |^## Authority Boundary$|^## Current Semantic Surface$|^## Validation Ownership$|^## Executable And Runtime-Plan Linkage$|^## Command Boundary Constraints$|^## Compile-Time Erasure And Source-Map Bridges$|workflow_command_adapter_contract\\.md|WORKFLOW_SEMANTIC_IR_SCHEMA_VERSION|LoadedWorkflowBundle\\.semantic_ir|workflow_semantic_ir\\(" docs/design/workflow_lisp_semantic_workflow_ir.md
```

## Task 3: Add Repo Discoverability Without Reopening The Parent Spec

**Files:**

- Modify: `docs/index.md`

- [ ] Add one concise `docs/index.md` entry describing the promoted doc as the durable shared Semantic IR contract surface for current Workflow Lisp/component-layer work.
- [ ] Place the new entry adjacent to the existing Workflow Lisp contract entries so readers discover Semantic IR next to Executable IR and the other component docs.
- [ ] Keep the edit narrow:
  - one new entry;
  - no broad index reshuffle;
  - no umbrella-spec surgery unless the Task 1 audit proves the existing parent-spec link is wrong.

**Blocking verification after Task 3:**

- [ ] Run:

```bash
rg -n "Workflow Lisp Semantic Workflow IR|workflow_lisp_semantic_workflow_ir\\.md" docs/index.md docs/design/workflow_lisp_frontend_specification.md
```

## Task 4: Verify The Promoted Docs Against Current Behavior

**Files:**

- No new files by default

- [ ] Re-read the promoted Semantic IR doc against the evidence modules and tests listed in `Fixed Inputs`.
- [ ] If the docs are accurate, stop at docs-only changes.
- [ ] Only if the promoted doc would otherwise be false, make the smallest corrective change in the real owner module or test and verify it with the narrowest existing selector first.

If corrective code or test work becomes necessary, start with these selectors:

```bash
python -m pytest tests/test_workflow_semantic_ir.py -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -q
```

If you add or rename any test module or selector while fixing a real mismatch, also run:

```bash
python -m pytest --collect-only tests/test_workflow_semantic_ir.py
python -m pytest --collect-only tests/test_workflow_lisp_build_artifacts.py
```

Expected outcome for the normal path: no Python or test edits are needed because the current checkout already implements the intended Semantic IR contract.

## Final Verification

- [ ] Re-run the design-gap prerequisite checks recorded in `state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/6/design-gap-architect/check_commands.json` so the implementation handoff retains the architecture evidence chain.
- [ ] Run this focused docs verification from the repo root:

```bash
rg -n "workflow_lisp_semantic_workflow_ir\\.md|SemanticWorkflowIR|LoadedWorkflowBundle\\.semantic_ir|workflow_semantic_ir\\(|workflow_command_adapter_contract\\.md|derived views|executable authority" \
  docs/design/workflow_lisp_semantic_workflow_ir.md \
  docs/index.md \
  docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/semantic-workflow-ir-durable-contract-surface/implementation_architecture.md \
  state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/6/design-gap-architect/work_item_context.md
```

- [ ] Record in the implementation handoff what changed and how it was verified.
- [ ] State explicitly whether docs-only verification was sufficient or whether a narrow corrective code/test change was required to keep the promoted contract truthful.
