# Executable IR Durable Contract Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining `executable-ir-durable-contract-surface` gap by adding one durable Executable IR design document, indexing it, and wiring one narrow umbrella-spec pointer so the current implemented executable authority surface is documented without reopening runtime or frontend behavior.

**Architecture:** Treat this as a docs-first, docs-mostly alignment pass over an already-landed implementation. `LoadedWorkflowBundle.ir` / `ExecutableWorkflow` remains the executable authority, while `runtime_plan`, `semantic_ir`, `source_map`, `workflow_boundary_projection`, and debug YAML remain derived views. The implementing agent should only touch Python or tests if a focused audit proves the drafted docs would otherwise be false for the current checkout.

**Tech Stack:** Markdown docs under `docs/design/` and `docs/`, current Workflow Lisp/runtime Python modules as evidence sources, `rg`, `sed`, and deterministic shell verification commands from the repo root.

---

## Fixed Inputs

Treat these as authority for scope and wording:

- `docs/design/workflow_lisp_unified_frontend_design.md`
  - `37. Executable IR Contract`
  - `46. Acceptance Gate for Component Architecture`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `0. Prerequisites, Boundaries, And Missing Internal Specs`
  - `48. Executable IR`
  - `49. Runtime Plan`
  - `74. Source Map Requirements`
  - `75. Runtime Observability`
  - `76. Build Artifacts`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/index.md`
- `docs/steering.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/work_instructions.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/executable-ir-durable-contract-surface/implementation_architecture.md`
- `state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/5/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/5/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-UNIFIED-DESIGN/progress_ledger.json`

Treat these as implementation evidence to keep the docs truthful:

- `orchestrator/workflow/executable_ir.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/workflow/runtime_plan.py`
- `orchestrator/workflow/semantic_ir.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/build.py`
- `tests/test_workflow_ir_lowering.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_diagnostics.py`

## Current Repo Baseline

Assume this exact starting point:

- `progress_ledger.json` has no events, so there is no later ledger evidence to override code/tests.
- `docs/steering.md` is empty, so it does not widen the selected slice.
- `orchestrator/workflow/executable_ir.py` already defines:
  - `WORKFLOW_EXECUTABLE_IR_SCHEMA_VERSION = "workflow_executable_ir.v1"`
  - `ExecutableWorkflow`
  - `workflow_executable_ir_to_json(...)`
  - `validate_executable_workflow(...)`
- `orchestrator/workflow/lowering.py` already validates executable IR before deriving runtime-plan and Semantic IR projections.
- `orchestrator/workflow/loaded_bundle.py` already exposes executable IR as `LoadedWorkflowBundle.ir`.
- `orchestrator/workflow/runtime_plan.py` and `orchestrator/workflow/semantic_ir.py` already derive non-authoritative projections from the validated executable layer.
- `orchestrator/workflow_lisp/compiler.py` already revalidates `bundle.ir` in the frontend `executable` pass.
- `orchestrator/workflow_lisp/build.py` already emits `executable_ir.json` and `runtime_plan.json`.
- `tests/test_workflow_ir_lowering.py`, `tests/test_workflow_lisp_build_artifacts.py`, and `tests/test_workflow_lisp_diagnostics.py` already prove schema/version, artifact emission, and executable-pass behavior.
- The missing gap is documentation surface and discoverability, not missing executable-layer code.

## Success Criteria

The work is complete only when all of the following are true:

- `docs/design/workflow_lisp_executable_ir.md` exists as the durable repo-level Executable IR contract doc.
- The new doc states that `LoadedWorkflowBundle.ir` / `ExecutableWorkflow` is authoritative.
- The new doc explicitly marks `runtime_plan`, `semantic_ir`, `source_map`, `workflow_boundary_projection`, and debug YAML as derived layers or views.
- The new doc references `docs/design/workflow_command_adapter_contract.md` for command-boundary meaning and constraints.
- `docs/index.md` has one discoverability entry for the new doc in the Workflow Lisp design section.
- `docs/design/workflow_lisp_frontend_specification.md` gains one narrow component-doc pointer to the new Executable IR doc inside the internal component-contract map.
- No unrelated design rewrites, backlog mutations, runtime changes, or new executable semantics are introduced.

## Scope Guardrails

Implement only the selected durable-contract-surface slice:

- create one durable component-contract doc under `docs/design/`;
- add one index entry in `docs/index.md`;
- add one narrow umbrella-spec pointer in `docs/design/workflow_lisp_frontend_specification.md`;
- keep the work docs-only unless a focused evidence audit proves a current doc statement would be false.

Explicit non-goals:

- new executable IR node kinds, schema behavior, or validator behavior;
- runtime closures, dynamic dispatch, runtime-native effects, or direct frontend-to-executable lowering;
- runtime-plan, semantic-IR, source-map, or executor behavior changes;
- new helper scripts, inline command glue, report-authority changes, or backlog/progress-ledger edits;
- broad restatement of the parent Workflow Lisp spec.

## File Map

**Create**

- `docs/design/workflow_lisp_executable_ir.md`

**Modify**

- `docs/index.md`
- `docs/design/workflow_lisp_frontend_specification.md`

**Evidence-only by default**

- `orchestrator/workflow/executable_ir.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/workflow/runtime_plan.py`
- `orchestrator/workflow/semantic_ir.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/build.py`
- `tests/test_workflow_ir_lowering.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_diagnostics.py`

## Required Content For The New Design Doc

Create `docs/design/workflow_lisp_executable_ir.md` with these sections in this order:

1. `# Workflow Lisp Executable IR`
2. `Status` and `Scope` lines that make the document current-checkout and component-contract oriented, not aspirational.
3. `## Purpose`
4. `## Authority Boundary`
5. `## Relationship To Adjacent Layers`
6. `## Current Executable Surface`
7. `## Validation Ownership`
8. `## Derived Layers`
9. `## Command Boundary Constraints`
10. `## Runtime-Value Erasure`
11. `## Build Artifacts And Evidence`
12. `## Out Of Scope`

The content must name the current code-level anchors directly:

- `ExecutableWorkflow`
- `WORKFLOW_EXECUTABLE_IR_SCHEMA_VERSION`
- `workflow_executable_ir_to_json(...)`
- `validate_executable_workflow(...)`
- `LoadedWorkflowBundle.ir`
- `derive_workflow_runtime_plan(...)`
- `derive_workflow_semantic_ir(...)`

The content must also say all of the following explicitly:

- the executable authority surface is validated executable IR, not debug YAML or runtime-plan summaries;
- command/provider semantics are not inferred from shell text and remain governed by `docs/design/workflow_command_adapter_contract.md`;
- compile-time-only values such as unresolved procedure references, `let-proc` metadata, syntax objects, and frontend-only structures must not survive into executable/runtime artifacts;
- future executable extensions require their own reviewed contract and must not be implied by this doc.

## Exact Discoverability Edits

Apply these narrow documentation edits:

- In `docs/index.md`, add one Workflow Lisp design entry for `design/workflow_lisp_executable_ir.md` adjacent to the other Workflow Lisp design-contract pages.
- In `docs/design/workflow_lisp_frontend_specification.md`, update the `Internal Component Contracts Required Before Runtime Implementation` list by inserting an `Executable IR` item immediately after `Semantic Workflow IR`.
- Renumber the remaining items in that list only as needed to keep the list sequential.
- Do not rewrite Part VIII or Section 48 beyond what is needed for discoverability.

## Task 1: Audit The Current Checkout Facts Before Writing

**Files:**

- No edits yet

- [ ] Confirm the current evidence anchors from the repo root:

```bash
rg -n "WORKFLOW_EXECUTABLE_IR_SCHEMA_VERSION|workflow_executable_ir_to_json|validate_executable_workflow" orchestrator/workflow/executable_ir.py
rg -n "validate_executable_workflow\\(ir\\)" orchestrator/workflow/lowering.py
rg -n "validate_executable_workflow\\(bundle\\.ir\\)" orchestrator/workflow_lisp/compiler.py
rg -n "executable_ir\\.json|runtime_plan\\.json" orchestrator/workflow_lisp/build.py tests/test_workflow_lisp_build_artifacts.py
```

- [ ] Re-read the existing architecture and ensure the plan stays aligned with its constraints:

```bash
sed -n '1,260p' docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/executable-ir-durable-contract-surface/implementation_architecture.md
sed -n '1,220p' state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/5/design-gap-architect/work_item_context.md
```

- [ ] If any evidence contradicts the baseline above, record the contradiction before editing docs. Do not silently widen scope.

## Task 2: Write The Durable Executable IR Contract Doc

**Files:**

- Create: `docs/design/workflow_lisp_executable_ir.md`

- [ ] Draft the new doc using the required section order above.
- [ ] Keep the prose implementation-aligned and repo-specific rather than describing hypothetical future layers as if they already existed.
- [ ] Reuse the authority language from the consumed inputs:
  - structured state and artifact values are authority;
  - reports and projections are views;
  - frontends lower through shared validation into shared semantic and executable layers.
- [ ] Reference `docs/design/workflow_command_adapter_contract.md` instead of restating command-adapter semantics as a competing authority source.
- [ ] Keep the doc bounded to the current executable layer. Do not redesign Core AST, Semantic IR, or runtime-plan contracts here.

**Blocking verification after Task 2:**

- [ ] Run:

```bash
rg -n "^# Workflow Lisp Executable IR$|^## Authority Boundary$|^## Validation Ownership$|^## Derived Layers$|^## Command Boundary Constraints$|^## Runtime-Value Erasure$|workflow_command_adapter_contract\\.md" docs/design/workflow_lisp_executable_ir.md
```

## Task 3: Add Discoverability Without Reopening The Parent Spec

**Files:**

- Modify: `docs/index.md`
- Modify: `docs/design/workflow_lisp_frontend_specification.md`

- [ ] Add one concise `docs/index.md` entry describing the new doc as the durable shared Executable IR contract for Workflow Lisp/component-layer work.
- [ ] Insert the new component-doc pointer in the frontend specification's internal contract list immediately after `Semantic Workflow IR`.
- [ ] Keep the frontend-spec edit narrow:
  - one new link entry;
  - minimal surrounding wording changes only if needed for grammar or numbering;
  - no broader restatement of executable semantics.

**Blocking verification after Task 3:**

- [ ] Run:

```bash
rg -n "Workflow Lisp Executable IR|workflow_lisp_executable_ir\\.md" docs/index.md docs/design/workflow_lisp_frontend_specification.md
```

## Task 4: Verify The Drafted Docs Against Current Behavior

**Files:**

- No new files by default

- [ ] Re-read the drafted doc against the evidence modules and tests listed in `Fixed Inputs`.
- [ ] If the docs are accurate, stop at docs-only changes.
- [ ] Only if the doc would otherwise be false, make the smallest corrective change in the real owner module and verify it with the narrowest existing selector first.

If corrective code or test work becomes necessary, start with these selectors:

```bash
python -m pytest tests/test_workflow_ir_lowering.py -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -q
python -m pytest tests/test_workflow_lisp_diagnostics.py -q
```

Expected outcome for the normal path: no Python changes are needed because the current checkout already satisfies the intended contract.

## Final Verification

- [ ] Run the deterministic artifact checks recorded in `state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/5/design-gap-architect/check_commands.json`.
- [ ] Run this focused docs verification from the repo root:

```bash
rg -n "workflow_lisp_executable_ir\\.md|LoadedWorkflowBundle\\.ir|ExecutableWorkflow|docs-first|docs-mostly|workflow_command_adapter_contract\\.md" \
  docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/executable-ir-durable-contract-surface/execution_plan.md \
  docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/executable-ir-durable-contract-surface/implementation_architecture.md \
  state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/5/design-gap-architect/work_item_context.md
```

- [ ] Record in the implementation handoff what changed and how it was verified.
- [ ] State explicitly that docs-only verification is sufficient unless the implementation path had to correct a real code/doc mismatch.
