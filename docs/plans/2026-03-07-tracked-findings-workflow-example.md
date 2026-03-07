# Tracked Findings Workflow Example Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a new example workflow that demonstrates stable finding tracking for a plan review/revise loop.

**Architecture:** Create a focused `1.4` example that drafts a plan from a design, reviews it against a carried-forward open-findings ledger, revises against structured findings, and exits when unresolved high findings reach zero. Keep the implementation scoped to example YAML, prompts, a small inline extraction command, workflow catalog docs, and one runtime smoke test.

**Tech Stack:** Workflow YAML, Codex provider prompts, inline Python command steps, pytest workflow smoke tests.

---

### Task 1: Add a failing workflow smoke test for tracked findings

**Files:**
- Modify: `tests/test_workflow_examples_v0.py`

**Step 1: Add the new example filename to the example load list**

Update `EXAMPLE_FILES` to include the new tracked-findings workflow.

**Step 2: Add a failing runtime smoke test**

Cover:
- one initial review that emits a high-severity unresolved finding
- one revise pass
- extraction of only unresolved findings into a carried-forward ledger
- a second review with zero unresolved high findings
- transition to workflow completion without a second revise pass

**Step 3: Run the targeted test to verify it fails before workflow/prompt files exist**

Run:
```bash
pytest tests/test_workflow_examples_v0.py::test_dsl_tracked_plan_review_loop_runtime -v
```

### Task 2: Add the tracked-findings example workflow and prompts

**Files:**
- Create: `workflows/examples/dsl_tracked_plan_review_loop.yaml`
- Create: `prompts/workflows/dsl_tracked_plan_review_loop/draft_plan.md`
- Create: `prompts/workflows/dsl_tracked_plan_review_loop/review_plan.md`
- Create: `prompts/workflows/dsl_tracked_plan_review_loop/revise_plan.md`

**Step 1: Implement a focused plan-only loop**

Add steps to:
- initialize cycle state and seed an empty open-findings ledger
- publish the design and seed ledger artifacts
- draft a plan
- prepare cycle-specific review and resolution artifact paths
- review with structured findings output
- gate on `decision == APPROVE` and `unresolved_high_count == 0`
- revise the plan against the latest review report
- increment the cycle counter
- extract unresolved findings for the next review pass

**Step 2: Keep artifact history cycle-specific**

Use cycle-numbered report and ledger paths so repeated review/revise passes do not overwrite the same on-disk files.

### Task 3: Update docs and make the test pass

**Files:**
- Modify: `workflows/README.md`
- Modify: `tests/test_workflow_examples_v0.py`

**Step 1: Add the new workflow to the workflow catalog**

Add a short description explaining that the example demonstrates stable finding tracking rather than fresh-prose-only review churn.

**Step 2: Run the targeted runtime test until it passes**

Run:
```bash
pytest tests/test_workflow_examples_v0.py::test_dsl_tracked_plan_review_loop_runtime -v
```

### Task 4: Run example validation checks

**Files:**
- No file changes

**Step 1: Run the example workflow module**

Run:
```bash
pytest tests/test_workflow_examples_v0.py -k tracked_plan_review -v
```

**Step 2: Run a workflow dry-run smoke check**

Run:
```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/dsl_tracked_plan_review_loop.yaml --dry-run
```

**Step 3: Run diff cleanliness checks for touched files**

Run:
```bash
git diff --check -- \
  docs/plans/2026-03-07-tracked-findings-workflow-example.md \
  workflows/examples/dsl_tracked_plan_review_loop.yaml \
  prompts/workflows/dsl_tracked_plan_review_loop/draft_plan.md \
  prompts/workflows/dsl_tracked_plan_review_loop/review_plan.md \
  prompts/workflows/dsl_tracked_plan_review_loop/revise_plan.md \
  workflows/README.md \
  tests/test_workflow_examples_v0.py
```
