# Provider Prompt Source Surface Clarity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Clarify and, if appropriate, incrementally improve the DSL/provider surface so prompt source fields such as `input_file` are not confused with workflow business inputs.

**Architecture:** Treat this as an abstraction-boundary cleanup, not a runtime behavior bug. First, tighten docs and authoring guidance so the repo consistently distinguishes workflow-boundary `inputs`, runtime data dependencies, and provider prompt sources. Then evaluate a compatibility-preserving surface improvement such as a clearer alias (`prompt_file` / `prompt_asset`) or advisory lint around misleading `input_file` usage, while keeping existing workflows valid.

**Tech Stack:** DSL/spec docs, provider/prompt authoring docs, workflow examples, Python linting/loader if a compatibility-preserving alias or warning is adopted, pytest docs/lint/example validation, orchestrator dry-run validation.

---

## Recommended Design

Recommended approach:
- clarify the abstraction split in docs first
- keep existing `input_file` / `asset_file` behavior for compatibility
- evaluate a clearer naming layer only after the docs are consistent
- if a new alias is added, keep it additive and back-compatible

Rejected alternatives:
- immediate rename/removal of `input_file`: too breaking and not justified by a runtime bug
- treat prompt sources as workflow `inputs`: wrong abstraction; they are provider-step prompt sources, not workflow business data
- leave the ambiguity entirely to tribal knowledge: author confusion will keep recurring

## Scope Boundaries

In scope:
- provider prompt-source terminology
- workflow author guidance about prompt assets vs workflow inputs
- example workflows that currently blur the layers
- optional additive alias/lint if the docs-only fix proves insufficient

Out of scope:
- changing prompt composition semantics
- changing dependency injection behavior
- changing workflow `inputs` / `outputs` data binding semantics

## Task Breakdown

### Task 1: Clarify the abstraction layers in docs and specs

**Files:**
- Modify: `specs/providers.md`
- Modify: `specs/dsl.md`
- Modify: `docs/workflow_drafting_guide.md`
- Modify: `docs/index.md` (only if a workflow-author fast-path note helps)

**Step 1: Clarify the provider prompt-source model**

Document in `specs/providers.md`:
- `input_file` and `asset_file` are prompt source surfaces for provider steps
- they are not workflow-boundary `inputs`
- `input_file` is historical naming, not business-data input semantics

**Step 2: Clarify the DSL surface split**

Document in `specs/dsl.md`:
- workflow `inputs` / `outputs` are typed workflow-boundary data
- `depends_on` / `consumes` are runtime data dependencies
- `input_file` / `asset_file` are provider prompt-source configuration

**Step 3: Update workflow author guidance**

Document in `docs/workflow_drafting_guide.md`:
- a short “do not confuse prompt source with workflow input” section
- preferred use of `asset_file` / `asset_depends_on` for bundled prompt assets in reusable workflows
- one bad-vs-better example

**Step 4: Read back the edited sections**

Run:

```bash
sed -n '1,120p' specs/providers.md
sed -n '100,180p' specs/dsl.md
sed -n '1,120p' docs/workflow_drafting_guide.md
```

Expected:
- all three docs use the same abstraction split

**Step 5: Commit**

```bash
git add specs/providers.md specs/dsl.md docs/workflow_drafting_guide.md docs/index.md
git commit -m "docs: clarify provider prompt source surfaces"
```

### Task 2: Audit examples for avoidable abstraction blur

**Files:**
- Modify: `workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml` (only if comments/docs blur layers)
- Modify: `workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml` (if present and relevant)
- Modify: `workflows/library/follow_on_plan_phase.yaml`
- Modify: `workflows/library/follow_on_implementation_phase.yaml`
- Modify: `workflows/README.md`

**Step 1: Review current examples**

Check for examples or comments that implicitly present prompt files as workflow inputs or business data instead of provider prompt sources.

**Step 2: Rewrite only the explanatory layer**

Update comments/README wording so examples distinguish:
- workflow inputs
- runtime dependencies
- prompt sources

Do not change working workflow behavior unless the example is actively misleading.

**Step 3: Run workflow validation and focused example tests**

Run:

```bash
pytest tests/test_workflow_examples_v0.py -k "workflow_examples_v0_load or follow_on_plan_impl_review_loop_v2" -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml --dry-run --input upstream_state_path=workflows/examples/inputs/dsl-follow-on-upstream-completed-state.json --input design_path=docs/plans/2026-03-06-dsl-evolution-control-flow-and-reuse.md --stream-output
```

Expected:
- examples still validate
- documentation-only cleanup does not break anything

**Step 4: Commit**

```bash
git add workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml workflows/library/follow_on_plan_phase.yaml workflows/library/follow_on_implementation_phase.yaml workflows/README.md
git commit -m "docs: separate workflow inputs from prompt sources in examples"
```

### Task 3: Evaluate a compatibility-preserving naming improvement

**Files:**
- Modify: `docs/backlog/active/2026-03-09-provider-prompt-source-surface-clarity.md`
- Optional future plan: `docs/plans/<future-date>-provider-prompt-source-alias.md`
- Potential implementation files if approved later:
  - `orchestrator/loader.py`
  - `tests/test_loader_validation.py`
  - `tests/test_workflow_examples_v0.py`

**Step 1: Decide whether docs are enough**

After Task 1 and Task 2, decide whether confusion remains high enough to justify a small DSL ergonomics improvement such as:
- additive alias `prompt_file` for `input_file`
- additive alias `prompt_asset` for `asset_file`
- advisory lint or docs-driven warning when reusable workflows use `input_file` for bundled prompts that should live on the asset surface

**Step 2: If an alias/lint is desired, spin a dedicated follow-up plan**

That later plan should cover:
- back-compat behavior
- precedence if both old and new names are present
- tests and example migration

**Step 3: Keep the current item scoped**

Do not mix a DSL rename into the initial docs-clarity pass unless there is strong evidence the docs fix is insufficient.

## Verification Summary

Minimum verification for the docs-first cleanup:

```bash
pytest tests/test_workflow_examples_v0.py -k "workflow_examples_v0_load or follow_on_plan_impl_review_loop_v2" -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml --dry-run --input upstream_state_path=workflows/examples/inputs/dsl-follow-on-upstream-completed-state.json --input design_path=docs/plans/2026-03-06-dsl-evolution-control-flow-and-reuse.md --stream-output
git diff --check
```

Expected:
- docs/examples are clearer about abstraction layers
- no behavior regressions are introduced
- the repo has a concrete follow-up path if a naming alias or lint is later justified
