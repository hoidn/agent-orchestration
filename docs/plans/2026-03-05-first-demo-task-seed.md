# First Demo Task Seed Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create the first task-specific seed repo for the workflow demo: a bounded Python-to-Rust ML-adjacent translation task that is hard enough to benefit from plan/review/fix loops but tractable for a single workflow run.

**Architecture:** Extend the generic demo scaffold into a task-specific seed under `examples/` with a purpose-built Python reference module, a Rust crate skeleton, and a canonical task fixture. Keep the module standard-library only so the difficulty comes from semantics and verification, not build tooling or dependency management.

**Tech Stack:** Markdown, Python 3.11+, Rust stable, Cargo, pytest.

---

## Difficulty Target

Target the middle difficulty band.

In scope:
- pure-Python reference code with no external dependencies
- pure-Rust library target with no FFI and no async
- ML-adjacent logic around classification metrics and calibration
- subtle but bounded semantics: tie-breaking, empty-bin handling, numeric tolerance, invalid-shape validation

Out of scope:
- NumPy, PyTorch, pandas, or ndarray-style tensors
- PyO3 or calling Python from Rust
- file formats, networking, concurrency, or large CLI surfaces
- open-ended optimization work

Success condition for task design:
- a direct single-shot run can produce a plausible but incomplete port
- a workflow run has a realistic chance to recover through one review/fix cycle
- hidden tests can check semantic parity precisely

### Task 1: Add failing tests for the seed repo

**Files:**
- Create: `tests/test_demo_task_seed.py`

**Step 1: Write failing tests**
- Assert the new seed repo exists under `examples/`
- Assert it contains the shared scaffold files plus task-specific Python and Rust files
- Assert the canonical task fixture describes a bounded Python-to-Rust ML port and explicitly avoids dependency/FFI work
- Assert visible checks are limited to tractable local commands

**Step 2: Run test to verify it fails**
Run: `pytest tests/test_demo_task_seed.py -q`
Expected: FAIL because the task-specific seed does not exist yet.

### Task 2: Create the task-specific seed repo

**Files:**
- Create: `examples/demo_task_multiclass_metrics_port/**`

**Step 1: Extend the scaffold**
- Copy the shared scaffold structure into the task-specific seed
- Keep `AGENTS.md`, `docs/index.md`, and planning templates aligned with the generic scaffold

**Step 2: Add task-specific reference files**
- Add a Python reference module for multiclass metrics/calibration
- Add a Rust crate skeleton with the intended API surface
- Add a canonical task markdown file that the provisioner can inject later

**Step 3: Add small visible checks**
- Include a tractable `cargo test` target and any minimal visible guidance needed for deriving checks
- Keep visible checks intentionally incomplete relative to the hidden evaluator

**Step 4: Run targeted tests**
Run: `pytest tests/test_demo_task_seed.py -q`
Expected: PASS.

### Task 3: Verify and commit

**Step 1: Run targeted verification**
Run: `pytest tests/test_demo_task_seed.py -q`
Expected: PASS.

**Step 2: Report the chosen difficulty level and why scratch beat OSS for the first seed**
