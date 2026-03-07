# nanoBragg Trial Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate the new nanoBragg seed and hidden evaluator into the direct-vs-workflow demo runner, provisioning flow, docs, and operator prompts so a full trial can be launched and graded the same way as the existing linear-classifier task.

**Architecture:** Reuse the current `provision_trial(...)` and `run_trial(...)` flow, add seed-specific evaluator dispatch for the new task, and extend the runbook/handoff docs with the new seed's commands and caveats. Keep the runner serial for now; the point of this plan is task integration, not runner concurrency.

**Tech Stack:** Python 3.11+, pathlib, json, subprocess, pytest, existing demo provisioning and trial-runner modules, Markdown runbooks.

---

### Task 1: Add failing runner tests for nanoBragg evaluator dispatch

**Files:**
- Modify: `tests/test_demo_trial_runner.py`
- Modify: `tests/test_demo_trial_runner_observability.py`
- Read: `orchestrator/demo/trial_runner.py`
- Read: `scripts/demo/evaluate_nanobragg_accumulation.py`

**Step 1: Extend the runner tests with a nanoBragg seed case**

Add tests that assert:
- `_select_evaluator(...)` chooses `scripts/demo/evaluate_nanobragg_accumulation.py` when:
  - `task_file.name == 'port_nanobragg_accumulation_to_pytorch.md'`, or
  - `seed_repo.name == 'demo_task_nanobragg_accumulation_port'`
- `run_trial(...)` writes `archive/evaluator/direct-result.json` and `archive/evaluator/workflow-result.json` for the nanoBragg seed the same way it does for the linear-classifier seed

Use the existing monkeypatched subprocess pattern. Do not require a real PyTorch run.

**Step 2: Run the runner tests to verify they fail**

Run:
```bash
pytest tests/test_demo_trial_runner.py tests/test_demo_trial_runner_observability.py -q
```

Expected:
- FAIL because the runner does not know about the nanoBragg evaluator yet.

**Step 3: Commit the failing tests only**

```bash
git add tests/test_demo_trial_runner.py tests/test_demo_trial_runner_observability.py
git commit -m "test: define nanoBragg runner dispatch"
```

### Task 2: Wire evaluator dispatch and trial metadata for the new seed

**Files:**
- Modify: `orchestrator/demo/trial_runner.py`
- Modify: `scripts/demo/run_trial.py`
- Modify: `tests/test_demo_trial_runner.py`
- Read: `scripts/demo/evaluate_nanobragg_accumulation.py`
- Read: `tests/test_demo_nanobragg_evaluator.py`

**Step 1: Implement the smallest evaluator selection change**

Extend `_select_evaluator(...)` in `orchestrator/demo/trial_runner.py` to return:
- `[sys.executable, str(_repo_root() / 'scripts' / 'demo' / 'evaluate_nanobragg_accumulation.py')]`
for the nanoBragg seed/task.

Do not redesign evaluator registration in this task.

**Step 2: Keep the archive shape unchanged**

Do not add new archive file names. Reuse:
- `archive/evaluator/status.json`
- `archive/evaluator/direct-result.json`
- `archive/evaluator/workflow-result.json`
- `archive/trial-result.json`

Only the selected evaluator command should differ.

**Step 3: Run the runner test suite**

Run:
```bash
pytest tests/test_demo_trial_runner.py tests/test_demo_trial_runner_observability.py -q
```

Expected:
- PASS.

**Step 4: Commit the runner integration**

```bash
git add orchestrator/demo/trial_runner.py scripts/demo/run_trial.py tests/test_demo_trial_runner.py tests/test_demo_trial_runner_observability.py
git commit -m "feat: integrate nanoBragg demo evaluator"
```

### Task 3: Add end-to-end provisioning and grading smoke coverage for the nanoBragg seed

**Files:**
- Create: `tests/test_demo_nanobragg_trial_smoke.py`
- Read: `tests/test_demo_trial_smoke.py`
- Read: `tests/test_demo_nanobragg_provisioning.py`
- Read: `scripts/demo/evaluate_nanobragg_accumulation.py`

**Step 1: Write a failing nanoBragg trial smoke test**

Create a smoke test that:
- provisions a temporary trial from `examples/demo_task_nanobragg_accumulation_port`
- monkeypatches the direct-arm subprocess, workflow subprocess, and nanoBragg evaluator subprocesses
- runs `run_trial(...)`
- asserts:
  - both workspaces are created
  - both commands are archived
  - the evaluator JSON results are written
  - `archive/trial-result.json` includes the nanoBragg seed path and evaluator verdicts

**Step 2: Run the smoke test to verify it fails**

Run:
```bash
pytest tests/test_demo_nanobragg_trial_smoke.py -q
```

Expected:
- FAIL until the evaluator dispatch and archive wiring are correct.

**Step 3: Implement only the glue needed to make the smoke test pass**

Prefer test helpers and minimal runner changes. Do not redesign the runner to be parallel or streaming in this task.

**Step 4: Run the focused integration suite**

Run:
```bash
pytest tests/test_demo_nanobragg_trial_smoke.py tests/test_demo_trial_runner.py tests/test_demo_trial_runner_observability.py -q
```

Expected:
- PASS.

**Step 5: Commit the smoke coverage**

```bash
git add tests/test_demo_nanobragg_trial_smoke.py tests/demo_helpers.py
git commit -m "test: add nanoBragg trial smoke coverage"
```

### Task 4: Update runbooks, prompts, and handoff docs for the new flagship task

**Files:**
- Modify: `docs/plans/2026-03-05-demo-scaffold-and-runbook.md`
- Modify: `docs/plans/2026-03-05-workflow-demo-session-handoff.md`
- Modify: `prompts/demo/run_direct_vs_workflow_trial.md`
- Modify: `prompts/demo/run_direct_arm_task.md`
- Read: `docs/plans/2026-03-05-nanobragg-subsystem-task-spec.md`
- Read: `docs/plans/2026-03-05-nanobragg-seed-workspace-implementation-plan.md`
- Read: `docs/plans/2026-03-05-nanobragg-hidden-evaluator-implementation-plan.md`

**Step 1: Document the new canonical seed and task file**

Update the runbook and handoff docs so they reference:
- `examples/demo_task_nanobragg_accumulation_port`
- `docs/tasks/port_nanobragg_accumulation_to_pytorch.md`
- `scripts/demo/evaluate_nanobragg_accumulation.py`

Keep the linear-classifier seed documented as a smaller baseline only.

**Step 2: Update the operator prompts for the new flagship task**

In `prompts/demo/run_direct_vs_workflow_trial.md` and `prompts/demo/run_direct_arm_task.md`, replace the linear-classifier-specific references with task-agnostic wording plus one explicit example line referencing the new nanoBragg seed.

Do not add hidden-evaluator hints to the prompts.

**Step 3: Run doc-adjacent verification**

Run:
```bash
pytest tests/test_demo_trial_runner.py tests/test_demo_nanobragg_trial_smoke.py -q
```

Expected:
- PASS.

**Step 4: Commit the doc and prompt updates**

```bash
git add docs/plans/2026-03-05-demo-scaffold-and-runbook.md \
  docs/plans/2026-03-05-workflow-demo-session-handoff.md \
  prompts/demo/run_direct_vs_workflow_trial.md \
  prompts/demo/run_direct_arm_task.md
git commit -m "docs: promote nanoBragg as demo flagship"
```

### Task 5: Final verification and first real trial record

**Files:**
- Verify: `tests/test_demo_task_nanobragg_seed.py`
- Verify: `tests/test_demo_nanobragg_provisioning.py`
- Verify: `tests/test_demo_nanobragg_evaluator.py`
- Verify: `tests/test_demo_nanobragg_evaluator_smoke.py`
- Verify: `tests/test_demo_nanobragg_trial_smoke.py`
- Verify: `tests/test_demo_trial_runner.py`
- Verify: `tests/test_demo_trial_runner_observability.py`
- Verify: `docs/plans/2026-03-05-workflow-demo-session-handoff.md`

**Step 1: Run the focused nanoBragg demo suite**

Run:
```bash
pytest tests/test_demo_task_nanobragg_seed.py \
  tests/test_demo_nanobragg_provisioning.py \
  tests/test_demo_nanobragg_evaluator.py \
  tests/test_demo_nanobragg_evaluator_smoke.py \
  tests/test_demo_nanobragg_trial_smoke.py \
  tests/test_demo_trial_runner.py \
  tests/test_demo_trial_runner_observability.py -q
```

Expected:
- PASS.

**Step 2: Dry-run the generic workflow again**

Run:
```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/generic_task_plan_execute_review_loop.yaml --dry-run
```

Expected:
- `[DRY RUN] Workflow validation successful`

**Step 3: Record one real nanoBragg trial invocation command in the handoff doc**

Add a command block showing:
```bash
python scripts/demo/run_trial.py \
  --seed-repo examples/demo_task_nanobragg_accumulation_port \
  --experiment-root /tmp/nanobragg-demo-trial \
  --task-file examples/demo_task_nanobragg_accumulation_port/docs/tasks/port_nanobragg_accumulation_to_pytorch.md \
  --direct-timeout-sec 1800 \
  --workflow-timeout-sec 3600
```

Do not claim the real trial passed unless it was actually run.

**Step 4: Commit the final integration sweep**

```bash
git add docs/plans/2026-03-05-workflow-demo-session-handoff.md
git commit -m "docs: finalize nanoBragg demo trial guidance"
```
