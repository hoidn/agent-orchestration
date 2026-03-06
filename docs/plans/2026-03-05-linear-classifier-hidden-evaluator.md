# Linear Classifier Hidden Evaluator Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a task-specific hidden evaluator for the linear-classifier demo seed that grades a completed workspace without mutating it.

**Architecture:** Implement a Python evaluator module under `orchestrator/demo/` plus a thin script wrapper under `scripts/demo/`. The evaluator will treat the visible Python reference as the oracle, generate a temporary Cargo harness outside the candidate workspace, depend on the workspace's `rust/` crate by path, run hidden differential tests, and emit a JSON verdict with failure categories plus a separate soft-quality report.

**Tech Stack:** Python 3.11+, pathlib, json, subprocess, tempfile, Rust stable, Cargo, pytest.

---

### Task 1: Add failing tests for evaluator behavior

**Files:**
- Create: `tests/test_demo_linear_classifier_evaluator.py`

**Step 1: Write failing tests**
- Verify a workspace with a correct Rust implementation produces `PASS`.
- Verify the current seed stub or another broken crate produces `FAIL` with a hidden-test failure category.
- Verify evaluation does not create files inside the candidate workspace.

**Step 2: Run tests to verify they fail**
Run: `pytest tests/test_demo_linear_classifier_evaluator.py -q`
Expected: FAIL because the evaluator module does not exist yet.

### Task 2: Implement evaluator module and script wrapper

**Files:**
- Create: `orchestrator/demo/evaluators/__init__.py`
- Create: `orchestrator/demo/evaluators/linear_classifier.py`
- Create: `scripts/demo/evaluate_linear_classifier.py`
- Test: `tests/test_demo_linear_classifier_evaluator.py`

**Step 1: Implement evaluator**
- Validate the workspace path and Rust crate layout.
- Load the visible Python reference as the oracle.
- Build a temporary hidden-test Cargo harness outside the candidate workspace.
- Depend on the candidate crate by path.
- Run hidden differential tests and capture stdout/stderr.
- Emit a JSON-ready result with hard verdict, summary, failure categories, and separate soft-quality findings.

**Step 2: Run targeted tests**
Run: `pytest tests/test_demo_linear_classifier_evaluator.py -q`
Expected: PASS.

### Task 3: Hook docs into the new evaluator

**Files:**
- Modify: `docs/plans/2026-03-05-demo-scaffold-and-runbook.md`

**Step 1: Add concrete evaluator command**
- Document the evaluator entrypoint for this specific task seed.

**Step 2: Run targeted tests**
Run: `pytest tests/test_demo_linear_classifier_evaluator.py -q`
Expected: PASS.

### Task 4: Verify and commit

**Step 1: Run verification**
Run: `pytest tests/test_demo_linear_classifier_evaluator.py -q`
Expected: PASS.

**Step 2: Report remaining gap**
- Note that the evaluator exists, but no end-to-end direct-vs-workflow trial runner exists yet.
