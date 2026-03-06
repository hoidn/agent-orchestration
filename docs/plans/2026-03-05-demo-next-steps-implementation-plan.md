# Workflow Demo Next Steps Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Finish the remaining demo infrastructure by adding a provisioned-workspace smoke test, a reproducible trial runner, and a second ML-adjacent Python-to-Rust task seed.

**Architecture:** Reuse the existing demo scaffold, provisioning helper, generic workflow YAML, and task-specific evaluator as the stable base. Add one thin orchestration layer that provisions a trial, launches the two arms, freezes and archives results, and invokes the hidden evaluator; then add a second task seed so the experiment is not overfit to the linear-classifier task.

**Tech Stack:** Python 3.11+, pathlib, json, subprocess, tempfile, pytest, git worktrees, Codex CLI, orchestrator CLI, Markdown seed docs, Rust seed crates.

---

### Task 1: Add a provisioned-workspace smoke test for the first seed

**Files:**
- Create: `tests/test_demo_trial_smoke.py`
- Modify: `tests/test_demo_linear_classifier_evaluator.py`
- Read: `orchestrator/demo/provisioning.py`
- Read: `orchestrator/demo/evaluators/linear_classifier.py`
- Read: `examples/demo_task_linear_classifier_port/docs/tasks/port_linear_classifier_to_rust.md`

**Step 1: Write the failing smoke test**

Write a new test that:
- creates a temporary git seed repo from `examples/demo_task_linear_classifier_port`
- provisions `direct-run/` and `workflow-run/` with `provision_trial`
- overwrites one workspace's `rust/src/lib.rs` with the known-good fixture from `tests/test_demo_linear_classifier_evaluator.py`
- evaluates the provisioned workspace through the public evaluator entrypoint
- asserts:
  - `state/task.md` exists in both run workspaces
  - the evaluator returns the expected JSON shape
  - the evaluator does not mutate the frozen workspace tree

Use monkeypatching for the Cargo invocation, as in the existing evaluator tests, so the smoke test is runnable in CI without a Rust toolchain.

**Step 2: Run the smoke test to verify it fails**

Run:
```bash
pytest tests/test_demo_trial_smoke.py -q
```

Expected:
- FAIL because the smoke test does not exist yet or the public evaluator entrypoint is not exercised end-to-end.

**Step 3: Implement the minimal shared helpers needed by the smoke test**

If the smoke test duplicates too much evaluator-test setup, extract only the smallest reusable helper(s) into:
- `tests/test_demo_linear_classifier_evaluator.py`
- or a new private helper module such as `tests/demo_helpers.py`

Do not add production code unless the failing test proves it is necessary.

**Step 4: Run the smoke test and targeted existing tests**

Run:
```bash
pytest tests/test_demo_trial_smoke.py tests/test_demo_linear_classifier_evaluator.py tests/test_demo_provisioning.py -q
```

Expected:
- PASS.

**Step 5: Commit**

```bash
git add tests/test_demo_trial_smoke.py tests/test_demo_linear_classifier_evaluator.py tests/test_demo_provisioning.py
git commit -m "test: add demo trial smoke coverage"
```

### Task 2: Add a runnable trial runner for direct-vs-workflow comparisons

**Files:**
- Create: `orchestrator/demo/trial_runner.py`
- Create: `scripts/demo/run_trial.py`
- Create: `tests/test_demo_trial_runner.py`
- Modify: `docs/plans/2026-03-05-demo-scaffold-and-runbook.md`
- Modify: `docs/plans/2026-03-05-workflow-demo-session-handoff.md`
- Read: `scripts/demo/provision_trial.py`
- Read: `orchestrator/demo/provisioning.py`
- Read: `workflows/examples/generic_task_plan_execute_review_loop.yaml`
- Read: `scripts/demo/evaluate_linear_classifier.py`

**Step 1: Write the failing runner tests**

Write tests for a pure-Python `run_trial(...)` API that monkeypatch subprocess boundaries and verify it:
- provisions from the requested seed repo and task file
- launches the direct arm with one prompt against `state/task.md`
- launches the workflow arm against `workflows/examples/generic_task_plan_execute_review_loop.yaml` with `--context task_source=state/task.md`
- writes archive metadata and per-arm command records under `<experiment-root>/archive/`
- runs the task-specific evaluator separately against both frozen workspaces
- emits a comparison JSON file such as `<experiment-root>/archive/trial-result.json`

The test should not require a real Codex binary or a real workflow run. Monkeypatch subprocess execution and assert the exact command lists and archive writes.

**Step 2: Run the failing tests**

Run:
```bash
pytest tests/test_demo_trial_runner.py -q
```

Expected:
- FAIL because `orchestrator/demo/trial_runner.py` and `scripts/demo/run_trial.py` do not exist yet.

**Step 3: Implement the minimal trial-runner API**

Implement `orchestrator/demo/trial_runner.py` with small, testable functions:
- `build_direct_command(...)`
- `build_workflow_command(...)`
- `archive_workspace_metadata(...)`
- `run_trial(...)`

The runner should:
- call `provision_trial(...)`
- execute the direct arm once in `direct-run/`
- execute the workflow arm once in `workflow-run/`
- freeze by recording `git status --short` and `git rev-parse HEAD || true`
- invoke `python scripts/demo/evaluate_linear_classifier.py <workspace>` for both arms when the selected seed is the linear-classifier seed
- persist one machine-readable comparison record

Keep seed-specific evaluator selection minimal for now. A simple dispatch table keyed by seed directory name is enough.

**Step 4: Add the CLI wrapper**

Implement `scripts/demo/run_trial.py` as a thin entrypoint over the Python API with flags:
- `--seed-repo`
- `--experiment-root`
- `--task-file`
- `--workflow`
- `--direct-prompt`
- `--commitish`

Default the workflow path to:
- `workflows/examples/generic_task_plan_execute_review_loop.yaml`

Default the direct prompt to:
- `Complete the repository task described in state/task.md. Follow AGENTS.md and docs/index.md.`

**Step 5: Verify the runner tests and existing demo tests**

Run:
```bash
pytest tests/test_demo_trial_runner.py tests/test_demo_trial_smoke.py tests/test_demo_linear_classifier_evaluator.py tests/test_demo_provisioning.py -q
```

Expected:
- PASS.

**Step 6: Update the runbook and handoff docs**

Add:
- the concrete `scripts/demo/run_trial.py` command
- the expected archive paths and result JSON location
- the seed-to-evaluator dispatch note

**Step 7: Commit**

```bash
git add orchestrator/demo/trial_runner.py scripts/demo/run_trial.py tests/test_demo_trial_runner.py docs/plans/2026-03-05-demo-scaffold-and-runbook.md docs/plans/2026-03-05-workflow-demo-session-handoff.md
git commit -m "feat: add demo trial runner"
```

### Task 3: Add a second ML-adjacent Python-to-Rust task seed

**Files:**
- Create: `examples/demo_task_sliding_window_port/AGENTS.md`
- Create: `examples/demo_task_sliding_window_port/README.md`
- Create: `examples/demo_task_sliding_window_port/docs/index.md`
- Create: `examples/demo_task_sliding_window_port/docs/dev_guidelines.md`
- Create: `examples/demo_task_sliding_window_port/docs/backlog/active/README.md`
- Create: `examples/demo_task_sliding_window_port/docs/backlog/done/.gitkeep`
- Create: `examples/demo_task_sliding_window_port/docs/plans/templates/artifact_contracts.md`
- Create: `examples/demo_task_sliding_window_port/docs/plans/templates/check_plan_schema.md`
- Create: `examples/demo_task_sliding_window_port/docs/plans/templates/plan_template.md`
- Create: `examples/demo_task_sliding_window_port/docs/plans/templates/review_template.md`
- Create: `examples/demo_task_sliding_window_port/docs/tasks/port_sliding_window_to_rust.md`
- Create: `examples/demo_task_sliding_window_port/src_py/README.md`
- Create: `examples/demo_task_sliding_window_port/src_py/sliding_window.py`
- Create: `examples/demo_task_sliding_window_port/rust/README.md`
- Create: `examples/demo_task_sliding_window_port/rust/Cargo.toml`
- Create: `examples/demo_task_sliding_window_port/rust/src/lib.rs`
- Create: `examples/demo_task_sliding_window_port/rust/tests/smoke_sliding_window.rs`
- Create: `examples/demo_task_sliding_window_port/artifacts/checks/.gitkeep`
- Create: `examples/demo_task_sliding_window_port/artifacts/review/.gitkeep`
- Create: `examples/demo_task_sliding_window_port/artifacts/work/.gitkeep`
- Create: `examples/demo_task_sliding_window_port/state/.gitkeep`
- Create: `tests/test_demo_task_sliding_window_seed.py`
- Modify: `docs/plans/2026-03-05-workflow-demo-session-handoff.md`
- Read: `examples/demo_task_linear_classifier_port/**`
- Read: `tests/test_demo_task_seed.py`

**Step 1: Write the failing seed-shape tests**

Model them on `tests/test_demo_task_seed.py`, but target the new seed. Assert:
- required shared scaffold files exist
- the task text is clearly Python-to-Rust, ML-adjacent, bounded, and dependency-light
- the Python reference avoids heavy libraries
- the Rust crate avoids heavy dependencies and FFI
- a visible smoke test exists

**Step 2: Run the seed tests to verify they fail**

Run:
```bash
pytest tests/test_demo_task_sliding_window_seed.py -q
```

Expected:
- FAIL because the new seed does not exist yet.

**Step 3: Create the new seed by cloning the linear-classifier pattern, not the exact task**

Use `examples/demo_task_linear_classifier_port/` as the scaffold reference.

The new task should be a deterministic sliding-window / patch-extraction utility with ML-adjacent semantics such as:
- fixed-size windows over 1-D or 2-D numeric sequences
- stride handling
- optional drop-last or pad behavior
- explicit edge-case rules

Keep the seed bounded:
- standard library only in Python and Rust
- no NumPy, pandas, torch, sklearn, PyO3, ndarray, or async/runtime dependencies
- visible smoke tests only; hidden evaluator can come later if the seed proves useful

**Step 4: Run the new seed tests plus the existing seed tests**

Run:
```bash
pytest tests/test_demo_task_sliding_window_seed.py tests/test_demo_task_seed.py -q
```

Expected:
- PASS.

**Step 5: Update the handoff doc**

Add the new seed to the file map and note that the task portfolio now contains at least two candidates.

**Step 6: Commit**

```bash
git add examples/demo_task_sliding_window_port tests/test_demo_task_sliding_window_seed.py docs/plans/2026-03-05-workflow-demo-session-handoff.md
git commit -m "feat: add sliding window demo task seed"
```

### Task 4: Final verification sweep

**Files:**
- Verify: `tests/test_demo_trial_smoke.py`
- Verify: `tests/test_demo_trial_runner.py`
- Verify: `tests/test_demo_linear_classifier_evaluator.py`
- Verify: `tests/test_demo_provisioning.py`
- Verify: `tests/test_demo_task_seed.py`
- Verify: `tests/test_demo_task_sliding_window_seed.py`

**Step 1: Run the focused demo test suite**

Run:
```bash
pytest \
  tests/test_demo_trial_smoke.py \
  tests/test_demo_trial_runner.py \
  tests/test_demo_linear_classifier_evaluator.py \
  tests/test_demo_provisioning.py \
  tests/test_demo_task_seed.py \
  tests/test_demo_task_sliding_window_seed.py -q
```

Expected:
- PASS.

**Step 2: Run workflow validation**

Run:
```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/generic_task_plan_execute_review_loop.yaml --dry-run
```

Expected:
- `[DRY RUN] Workflow validation successful`

**Step 3: Record the remaining gap explicitly**

Document in the final status note whether the new runner has been exercised only with mocked subprocesses or also with a real local direct/workflow trial.

**Step 4: Commit any final documentation-only cleanup**

```bash
git add docs/plans/2026-03-05-demo-scaffold-and-runbook.md docs/plans/2026-03-05-workflow-demo-session-handoff.md
git commit -m "docs: finalize demo next-step runbook notes"
```
