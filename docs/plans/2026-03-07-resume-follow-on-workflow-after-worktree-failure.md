# Resume Follow-On Workflow After Worktree Failure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent the follow-on implementation step from escaping into a git worktree, merge the already-produced batch work onto the checked out branch, and resume the failed workflow safely.

**Architecture:** Keep the fix narrowly scoped to the implementation prompt and operational recovery steps. Preserve run-state artifacts needed for `orchestrate resume`, temporarily park unrelated tracked dirt that would block merge/recovery, then resume the existing run with live output.

**Tech Stack:** Markdown prompts, git, tmux, orchestrator CLI

---

### Task 1: Patch the implementation prompt

**Files:**
- Modify: `prompts/workflows/dsl_follow_on_plan_impl_loop/implement_plan.md`

**Step 1: Add explicit run-workspace authority**

Instruct the implementation step that:
- the authoritative workspace is the workflow run workspace root
- it must not create or switch into any git worktree
- it must keep output-contract files in the run workspace paths

**Step 2: Add dirty-tree cleanup guidance**

Instruct the implementation step that if the run workspace is dirty, it must clean the run workspace state before implementation instead of escaping to another workspace.

**Step 3: Keep the existing execution/report contract**

Retain the existing requirements to:
- follow `executing-plans`
- write the execution report to `state/execution_report_path.txt`
- stage and commit with a descriptive message

### Task 2: Preserve resume state while cleaning merge blockers

**Files:**
- Preserve: `.orchestrate/runs/20260307T084343Z-mbzxdl/**`
- Preserve: `state/**`
- Preserve: `artifacts/**`

**Step 1: Park unrelated tracked modifications**

Stash tracked changes that are unrelated to the recovery and would interfere with merging the batch branch.

**Step 2: Preserve run artifacts**

Do not stash or delete the run-state directories and workspace files the failed run needs for `resume`.

### Task 3: Merge the implementation work

**Files:**
- Merge from branch: `feat/dsl-evolution-batch1`

**Step 1: Merge the branch into the checked out branch**

Bring the batch implementation commits onto the checked out branch without restarting the workflow.

**Step 2: Resolve any conflicts minimally**

If conflicts occur, keep the recovery scoped to the implementation batch and prompt fix.

### Task 4: Verify and resume

**Files:**
- Verify: `prompts/workflows/dsl_follow_on_plan_impl_loop/implement_plan.md`
- Verify: `.orchestrate/runs/20260307T084343Z-mbzxdl/state.json`

**Step 1: Run narrow verification**

Run at least:
- `git diff --check`
- a relevant orchestrator dry-run or other narrow smoke check for the workflow/prompt surface

**Step 2: Resume in tmux with live output**

Use `orchestrate resume 20260307T084343Z-mbzxdl --stream-output` in tmux so the resumed step can be monitored without restarting the workflow.
