# Demo Provisioning Script Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a small, testable provisioning utility that stamps out `seed/`, `direct-run/`, and `workflow-run/` from one git commit and injects the same task artifact into both run workspaces.

**Architecture:** Implement the logic in a new Python module under `orchestrator/demo/` so it is importable and testable, then add a thin script entrypoint under `scripts/demo/`. Use git worktrees for isolation and shared commit provenance. Keep scope limited to provisioning and metadata recording; launching and grading remain separate steps.

**Tech Stack:** Python 3.11+, pathlib, argparse, subprocess, git, pytest.

---

### Task 1: Add failing tests for provisioning behavior

**Files:**
- Create: `tests/test_demo_provisioning.py`
- Reference: `docs/plans/2026-03-05-demo-scaffold-and-runbook.md`

**Step 1: Write failing tests**
- Cover provisioning from a temp git repo into `seed/`, `direct-run/`, and `workflow-run/`.
- Cover identical task injection into `state/task.md` in both run workspaces.
- Cover recording the start commit SHA in each workspace.
- Cover refusal to provision into a non-empty experiment root without an explicit force/cleanup mode.

**Step 2: Run test to verify it fails**
Run: `pytest tests/test_demo_provisioning.py -q`
Expected: FAIL because the provisioning module does not exist yet.

### Task 2: Implement the provisioning module

**Files:**
- Create: `orchestrator/demo/__init__.py`
- Create: `orchestrator/demo/provisioning.py`
- Test: `tests/test_demo_provisioning.py`

**Step 1: Write minimal implementation**
- Implement argument parsing and a `provision_trial(...)` function.
- Inputs: seed repo path, experiment root, task file path, optional commit-ish.
- Behavior:
  - resolve commit SHA from seed repo
  - create sibling worktrees at `seed/`, `direct-run/`, `workflow-run/`
  - create `archive/` and `evaluator/` directories
  - write identical `state/task.md` into `direct-run/` and `workflow-run/`
  - optionally mirror task into `docs/backlog/active/task.md` when that path exists
  - write a metadata file recording paths and start commit SHA

**Step 2: Run targeted tests**
Run: `pytest tests/test_demo_provisioning.py -q`
Expected: PASS.

### Task 3: Add a runnable script wrapper

**Files:**
- Create: `scripts/demo/provision_trial.py`
- Modify: `docs/plans/2026-03-05-demo-scaffold-and-runbook.md`

**Step 1: Add thin wrapper**
- Make the script call `orchestrator.demo.provisioning.main()`.
- Keep it free of business logic.

**Step 2: Update runbook with concrete command**
- Add the exact recommended provisioning command.

**Step 3: Run targeted tests**
Run: `pytest tests/test_demo_provisioning.py -q`
Expected: PASS.

### Task 4: Verify repository state

**Files:**
- Verify only targeted files are staged.

**Step 1: Run verification**
Run: `pytest tests/test_demo_provisioning.py -q`
Expected: PASS.

**Step 2: Record final command and outputs in the response**
- Mention that only targeted provisioning files were changed.
