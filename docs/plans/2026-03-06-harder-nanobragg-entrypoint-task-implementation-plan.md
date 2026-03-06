# Harder nanoBragg Entrypoint Task Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current thin nanoBragg accumulation task with a harder, harness-backed task that asks the agent to port effectively the whole substantive `nanoBragg.c` simulation path by matching one extracted C entrypoint.

**Architecture:** Build a standalone C reference harness around a new program-level entrypoint extracted from the post-parse path inside `../nanoBragg/golden_suite_generator/nanoBragg.c`'s `main`, then derive the visible seed, hidden evaluator, and trial integration from that harness. Verification should still be one entrypoint call, but that call chain should reach most of the substantive simulation logic in the file. The task prompt should name the entrypoint and source region, not restate the implementation semantics as a detailed public contract.

**Tech Stack:** C reference harness, Python fixture/corpus generation, PyTorch target seed, pytest, hidden evaluator CLI, agent-orchestration demo runner.

---

### Task 1: Lock The Entrypoint And Scope

**Files:**
- Create: `docs/plans/2026-03-06-harder-nanobragg-entrypoint-design.md`
- Reference: `../nanoBragg/golden_suite_generator/nanoBragg.c`
- Reference: `docs/plans/2026-03-05-nanobragg-subsystem-task-spec.md`

**Step 1: Write the design note**

Document:
- the exact source region to extract, centered on the post-parse simulation path inside `main` rather than the narrow detector pixel loop
- the recommended public C entrypoint name, for example `nanobragg_run`
- exact inputs and outputs of that entrypoint
- which surrounding helper logic stays inside the harness versus becomes precomputed fixture data
- why this entrypoint is considered a "whole substantive file via one call chain" task rather than a kernel task

**Step 2: Constrain the entrypoint**

State these boundaries explicitly:
- output is the detector `floatimage` tensor for the selected ROI/full image
- inputs are raw experiment-description inputs needed by the extracted simulation path, not precomputed kernel tensors
- no CLI/config-file parsing
- no image writing
- no unrelated noise paths
- no full-program initialization flow
- yes to broad internal reachability across the simulation logic

**Step 3: Define the seed-facing task statement**

Write the one-paragraph task statement that future agents will see:
- identify the named entrypoint
- identify the source file and the extracted high-level simulation region
- require PyTorch implementation matching the extracted entrypoint outputs
- require restructuring away from a naive scalar translation where practical
- do not include a long public contract checklist

**Step 4: Commit**

```bash
git add docs/plans/2026-03-06-harder-nanobragg-entrypoint-design.md
git commit -m "docs: define harder nanobragg entrypoint task"
```

### Task 2: Build The Standalone C Reference Harness

**Files:**
- Create: `scripts/demo/nanobragg_entrypoint_reference/reference_harness.c`
- Create: `scripts/demo/nanobragg_entrypoint_reference/reference_harness.h`
- Create: `scripts/demo/nanobragg_entrypoint_reference/build_harness.py`
- Create: `scripts/demo/nanobragg_entrypoint_reference/run_reference_case.py`
- Test: `tests/test_demo_nanobragg_entrypoint_reference_harness.py`

**Step 1: Write the failing harness smoke test**

Create a test that expects:
- the harness can be built from source
- the harness exposes one callable entrypoint
- one tiny fixture can be executed end-to-end and returns an output tensor blob of the expected shape

**Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_demo_nanobragg_entrypoint_reference_harness.py -q
```

Expected:
- failure because the harness files and runner do not exist yet

**Step 3: Implement the standalone harness**

Build a minimal extraction layer that:
- isolates the chosen high-level simulation path from `nanoBragg.c`
- wraps it in a named function such as `nanobragg_run`
- accepts structured inputs from a fixture blob or simple C structs
- writes only the detector image output needed by the task

Do not add unrelated program behavior.

**Step 4: Implement the Python build/run wrapper**

`build_harness.py` should:
- compile the harness deterministically
- write the binary/artifact path to a predictable location

`run_reference_case.py` should:
- load one structured input case
- execute the harness
- emit machine-readable outputs for the evaluator/corpus builder

**Step 5: Re-run the harness smoke test**

Run:

```bash
pytest tests/test_demo_nanobragg_entrypoint_reference_harness.py -q
```

Expected:
- PASS

**Step 6: Commit**

```bash
git add scripts/demo/nanobragg_entrypoint_reference tests/test_demo_nanobragg_entrypoint_reference_harness.py
git commit -m "feat: add nanobragg entrypoint reference harness"
```

### Task 3: Define The Structured Fixture Format

**Files:**
- Create: `examples/demo_task_nanobragg_entrypoint_port/fixtures/visible/README.md`
- Create: `orchestrator/demo/evaluators/fixtures/nanobragg_entrypoint/README.md`
- Create: `scripts/demo/build_nanobragg_entrypoint_cases.py`
- Test: `tests/test_demo_nanobragg_entrypoint_fixture_schema.py`

**Step 1: Write the failing fixture-schema test**

The test should require:
- one visible fixture directory for the new seed
- one hidden fixture directory for evaluator cases
- shared documented top-level keys across both
- explicit output-shape metadata
- explicit provenance fields for hidden cases

**Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_demo_nanobragg_entrypoint_fixture_schema.py -q
```

Expected:
- failure because the new fixture schema/docs do not exist yet

**Step 3: Define the fixture format**

Keep it narrow:
- entrypoint inputs only
- output shape metadata
- optional trace taps
- provenance only in hidden cases

Do not restate implementation semantics in the visible fixture docs.

**Step 4: Implement the case builder**

`build_nanobragg_entrypoint_cases.py` should:
- generate visible smoke fixtures
- generate hidden evaluator fixtures
- derive hidden expected outputs by calling `run_reference_case.py`

**Step 5: Re-run schema test**

Run:

```bash
pytest tests/test_demo_nanobragg_entrypoint_fixture_schema.py -q
```

Expected:
- PASS

**Step 6: Commit**

```bash
git add examples/demo_task_nanobragg_entrypoint_port/fixtures orchestrator/demo/evaluators/fixtures/nanobragg_entrypoint scripts/demo/build_nanobragg_entrypoint_cases.py tests/test_demo_nanobragg_entrypoint_fixture_schema.py
git commit -m "feat: add nanobragg entrypoint fixture schema"
```

### Task 4: Build The New Seed Repo

**Files:**
- Create: `examples/demo_task_nanobragg_entrypoint_port/AGENTS.md`
- Create: `examples/demo_task_nanobragg_entrypoint_port/docs/index.md`
- Create: `examples/demo_task_nanobragg_entrypoint_port/docs/dev_guidelines.md`
- Create: `examples/demo_task_nanobragg_entrypoint_port/docs/tasks/port_nanobragg_entrypoint_to_pytorch.md`
- Create: `examples/demo_task_nanobragg_entrypoint_port/src_c/nanoBragg.c`
- Create: `examples/demo_task_nanobragg_entrypoint_port/src_c/README.md`
- Create: `examples/demo_task_nanobragg_entrypoint_port/torch_port/__init__.py`
- Create: `examples/demo_task_nanobragg_entrypoint_port/torch_port/entrypoint.py`
- Create: `examples/demo_task_nanobragg_entrypoint_port/torch_port/types.py`
- Create: `examples/demo_task_nanobragg_entrypoint_port/tests/test_smoke_entrypoint.py`
- Test: `tests/test_demo_task_nanobragg_entrypoint_seed.py`

**Step 1: Write the failing seed-layout test**

Require:
- the new seed tree exists
- the task file names the chosen entrypoint and source region
- the visible test entrypoint exists
- the visible docs describe boundaries without restating a full hidden contract

**Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_demo_task_nanobragg_entrypoint_seed.py -q
```

Expected:
- failure because the new seed does not exist yet

**Step 3: Build the seed**

The visible task should say only:
- implement `torch_port.entrypoint.<function_name>`
- match the named C entrypoint outputs
- use the visible fixtures and extracted source region
- keep the port scoped
- derive and run strong local pytest checks

The visible task should also make clear that this is a substantial entrypoint covering most of the program's simulation behavior, not a narrow detector kernel.

Do not expose a long public contract checklist.

**Step 4: Add minimal visible smoke checks**

`tests/test_smoke_entrypoint.py` should cover:
- output shape
- finite values
- one or two simple trace taps

Visible tests should be necessary but insufficient.

**Step 5: Re-run seed-layout test**

Run:

```bash
pytest tests/test_demo_task_nanobragg_entrypoint_seed.py -q
pytest --collect-only -q tests/test_demo_task_nanobragg_entrypoint_seed.py examples/demo_task_nanobragg_entrypoint_port/tests/test_smoke_entrypoint.py
```

Expected:
- PASS

**Step 6: Commit**

```bash
git add examples/demo_task_nanobragg_entrypoint_port tests/test_demo_task_nanobragg_entrypoint_seed.py
git commit -m "feat: add harder nanobragg entrypoint seed"
```

### Task 5: Add The Hidden Evaluator

**Files:**
- Create: `orchestrator/demo/evaluators/nanobragg_entrypoint.py`
- Create: `scripts/demo/evaluate_nanobragg_entrypoint.py`
- Test: `tests/test_demo_nanobragg_entrypoint_evaluator.py`
- Test: `tests/test_demo_nanobragg_entrypoint_evaluator_smoke.py`

**Step 1: Write the failing evaluator tests**

Require:
- evaluator can load the hidden cases
- evaluator compares candidate output tensors against harness-derived reference tensors
- evaluator reports structured per-case failures

**Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_demo_nanobragg_entrypoint_evaluator.py tests/test_demo_nanobragg_entrypoint_evaluator_smoke.py -q
```

Expected:
- failure because evaluator files do not exist yet

**Step 3: Implement evaluator**

The evaluator should:
- import the candidate PyTorch entrypoint from the workspace
- execute visible/hidden cases
- compare outputs with `torch.testing.assert_close`
- report case IDs, shapes, dtype mismatches, and max-error summaries

**Step 4: Re-run evaluator tests**

Run:

```bash
pytest tests/test_demo_nanobragg_entrypoint_evaluator.py tests/test_demo_nanobragg_entrypoint_evaluator_smoke.py -q
```

Expected:
- PASS

**Step 5: Commit**

```bash
git add orchestrator/demo/evaluators/nanobragg_entrypoint.py scripts/demo/evaluate_nanobragg_entrypoint.py tests/test_demo_nanobragg_entrypoint_evaluator.py tests/test_demo_nanobragg_entrypoint_evaluator_smoke.py
git commit -m "feat: add nanobragg entrypoint hidden evaluator"
```

### Task 6: Integrate Provisioning And Trial Runner

**Files:**
- Modify: `orchestrator/demo/trial_runner.py`
- Modify: `orchestrator/demo/provisioning.py`
- Modify: `scripts/demo/provision_trial.py`
- Modify: `scripts/demo/run_trial.py`
- Test: `tests/test_demo_trial_runner.py`
- Test: `tests/test_demo_provisioning.py`
- Test: `tests/test_demo_trial_smoke.py`

**Step 1: Write the failing integration test**

Add one test that requires:
- evaluator dispatch by new task file / seed name
- staged workflow assets for the new seed
- one smoke trial archive path for the new seed

**Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_demo_trial_runner.py tests/test_demo_provisioning.py tests/test_demo_trial_smoke.py -q
```

Expected:
- failure on the new nanobragg entrypoint path

**Step 3: Implement integration**

Update the demo runner/provisioner so the new seed:
- provisions cleanly
- selects the new hidden evaluator
- archives results under the existing direct-vs-workflow machinery

**Step 4: Re-run targeted integration tests**

Run:

```bash
pytest tests/test_demo_trial_runner.py tests/test_demo_provisioning.py tests/test_demo_trial_smoke.py -q
```

Expected:
- PASS

**Step 5: Re-run one orchestrator/demo smoke**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/generic_task_plan_execute_review_loop.yaml --dry-run
```

Expected:
- `[DRY RUN] Workflow validation successful`

**Step 6: Commit**

```bash
git add orchestrator/demo/trial_runner.py orchestrator/demo/provisioning.py scripts/demo/provision_trial.py scripts/demo/run_trial.py tests/test_demo_trial_runner.py tests/test_demo_provisioning.py tests/test_demo_trial_smoke.py
git commit -m "feat: integrate harder nanobragg entrypoint trial"
```

### Task 7: Replace The Current Flagship Documentation

**Files:**
- Modify: `docs/plans/2026-03-05-workflow-demo-design.md`
- Modify: `docs/plans/2026-03-05-workflow-demo-session-handoff.md`
- Modify: `docs/plans/2026-03-05-demo-scaffold-and-runbook.md`
- Modify: `docs/plans/2026-03-05-nanobragg-subsystem-task-spec.md`

**Step 1: Update docs**

Document:
- why the new task is harder
- the chosen entrypoint name and source span
- why the public task is now “match the entrypoint outputs” instead of “follow a detailed public contract”
- how visible fixtures, hidden evaluator, and workflow prompts stay aligned without spoon-feeding the implementation

**Step 2: Verify docs by reading for internal consistency**

Run:

```bash
rg -n "nanobragg entrypoint|port_nanobragg_entrypoint_to_pytorch|evaluate_nanobragg_entrypoint" docs/plans
```

Expected:
- all intended references present

**Step 3: Commit**

```bash
git add docs/plans/2026-03-05-workflow-demo-design.md docs/plans/2026-03-05-workflow-demo-session-handoff.md docs/plans/2026-03-05-demo-scaffold-and-runbook.md docs/plans/2026-03-05-nanobragg-subsystem-task-spec.md
git commit -m "docs: switch flagship task to nanobragg entrypoint port"
```

### Task 8: Run The First Real Comparison Trial

**Files:**
- No new repo files required
- Outputs land under a fresh `/tmp/...` experiment root

**Step 1: Provision and launch one real trial**

Run:

```bash
python scripts/demo/run_trial.py \
  --seed-repo examples/demo_task_nanobragg_entrypoint_port \
  --experiment-root /tmp/nanobragg-entrypoint-demo-trial \
  --task-file examples/demo_task_nanobragg_entrypoint_port/docs/tasks/port_nanobragg_entrypoint_to_pytorch.md \
  --direct-provider codex \
  --direct-model gpt-5.3-codex \
  --direct-effort medium \
  --workflow-provider codex \
  --workflow-model gpt-5.3-codex \
  --workflow-effort medium
```

**Step 2: Record outcomes**

Capture:
- direct hidden verdict
- workflow hidden verdict
- visible-check counts
- archive paths
- whether the task is now hard enough to separate direct from workflow

**Step 3: If both pass too easily, tighten only by widening the hidden corpus**

Do not immediately broaden the public task wording again. First increase hidden-case diversity around the same entrypoint.

**Step 4: Commit follow-up docs if needed**

```bash
git add docs/plans/2026-03-05-workflow-demo-session-handoff.md
git commit -m "docs: record first nanobragg entrypoint trial results"
```

Plan complete and saved to `docs/plans/2026-03-06-harder-nanobragg-entrypoint-task-implementation-plan.md`. Two execution options:

1. Subagent-Driven (this session) - I dispatch fresh subagent per task, review between tasks, fast iteration

2. Parallel Session (separate) - Open new session with `executing-plans`, batch execution with checkpoints

Which approach?
