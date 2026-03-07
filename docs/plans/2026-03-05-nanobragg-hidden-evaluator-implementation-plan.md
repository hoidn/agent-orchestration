# nanoBragg Hidden Evaluator Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a deterministic hidden evaluator for the nanoBragg accumulation task, backed by a fixed corpus of hidden reference cases and tensor-level parity checks against the agent-produced PyTorch module.

**Architecture:** Follow the existing `linear_classifier` evaluator pattern: a repo-local evaluator module plus a thin CLI wrapper under `scripts/demo/`. Keep hidden assets outside the visible task seed. Use precomputed hidden fixtures and expected outputs checked into the main repo, not generated at trial time.

**Tech Stack:** Python 3.11+, PyTorch (preinstalled in the trial environment), pytest, JSON fixture metadata, temporary evaluation harnesses, existing `orchestrator.demo.evaluators` package.

---

### Task 1: Add failing tests for the hidden evaluator contract

**Files:**
- Create: `tests/test_demo_nanobragg_evaluator.py`
- Read: `tests/test_demo_linear_classifier_evaluator.py`
- Read: `orchestrator/demo/evaluators/linear_classifier.py`
- Read: `docs/plans/2026-03-05-nanobragg-subsystem-task-spec.md`

**Step 1: Write the failing evaluator tests**

Model `tests/test_demo_nanobragg_evaluator.py` on `tests/test_demo_linear_classifier_evaluator.py`, but target a PyTorch workspace layout. Add tests that assert:
- `evaluate_workspace(...)` returns JSON-compatible fields:
  - `verdict`
  - `failure_categories`
  - `summary.hidden_tests_passed`
  - `soft_quality.score`
- a workspace with missing `torch_port/accumulation.py` fails with a task-specific category such as `missing_target_module`
- a workspace with a deliberately wrong tensor result fails with `hidden_acceptance_failed`
- a workspace with the expected module API and correct tensors passes

Use monkeypatching to keep the tests local and deterministic. Do not shell out to the full trial runner in this task.

**Step 2: Run the evaluator test to verify it fails**

Run:
```bash
pytest tests/test_demo_nanobragg_evaluator.py -q
```

Expected:
- FAIL because the evaluator module and hidden fixtures do not exist yet.

**Step 3: Capture the expected failure categories in the test file comments**

Document the intended categories directly in the test file so future implementers do not invent new names during implementation.

**Step 4: Commit the failing tests only**

```bash
git add tests/test_demo_nanobragg_evaluator.py
git commit -m "test: define nanoBragg hidden evaluator contract"
```

### Task 2: Add the hidden fixture corpus and reference metadata

**Files:**
- Create: `orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/README.md`
- Create: `orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/cases.json`
- Create: `orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/expected_case_small.pt`
- Create: `orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/expected_case_thickness.pt`
- Create: `orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/expected_case_mosaic.pt`
- Create: `scripts/demo/build_nanobragg_reference_cases.py`
- Read: `../nanoBragg/golden_suite_generator/nanoBragg.c`
- Read: `docs/plans/2026-03-05-nanobragg-subsystem-task-spec.md`

**Step 1: Add a schema-first README and `cases.json`**

Define the hidden case metadata schema in `README.md` and `cases.json`. Each case record should include:
- `case_id`
- `input_fixture_relpath`
- `expected_tensor_relpath`
- `rtol`
- `atol`
- optional `trace_taps`
- optional `notes`

Keep `input_fixture_relpath` pointing to workspace-visible fixture files where possible so the evaluator can combine visible inputs with hidden expected outputs.

**Step 2: Add a one-off builder script for regenerating hidden expected tensors**

Create `scripts/demo/build_nanobragg_reference_cases.py` that:
- reads the hidden case metadata
- loads the visible input fixtures from a provisioned or seed workspace
- writes the expected `.pt` tensors into `orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/`

The script is a maintenance tool only. It is not part of trial runtime.

**Step 3: Generate and store three hidden expected outputs**

Produce at least:
- `expected_case_small.pt`
- `expected_case_thickness.pt`
- `expected_case_mosaic.pt`

Do not store these in the visible seed.

**Step 4: Run a focused schema sanity check**

Run:
```bash
python - <<'PY'
import json
from pathlib import Path
path = Path('orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/cases.json')
payload = json.loads(path.read_text())
assert isinstance(payload['cases'], list)
assert len(payload['cases']) >= 3
print('ok')
PY
```

Expected:
- `ok`

**Step 5: Commit the hidden corpus assets**

```bash
git add orchestrator/demo/evaluators/fixtures/nanobragg_accumulation \
  scripts/demo/build_nanobragg_reference_cases.py
git commit -m "feat: add nanoBragg hidden evaluator corpus"
```

### Task 3: Implement the evaluator module and CLI entrypoint

**Files:**
- Create: `orchestrator/demo/evaluators/nanobragg_accumulation.py`
- Create: `scripts/demo/evaluate_nanobragg_accumulation.py`
- Modify: `orchestrator/demo/evaluators/__init__.py`
- Read: `orchestrator/demo/evaluators/linear_classifier.py`
- Read: `scripts/demo/evaluate_linear_classifier.py`
- Read: `tests/test_demo_nanobragg_evaluator.py`

**Step 1: Run the evaluator tests again**

Run:
```bash
pytest tests/test_demo_nanobragg_evaluator.py -q
```

Expected:
- FAIL because the module and CLI still do not exist.

**Step 2: Implement the minimal evaluator API**

Add:
- `load_hidden_cases(...)`
- `load_workspace_module(...)`
- `evaluate_workspace(...)`
- `main(...)`

The evaluator should:
- import the workspace's `torch_port.accumulation` module in isolation
- run each hidden case through the workspace implementation
- compare tensors with `torch.testing.assert_close`
- accumulate per-case failures into the structured verdict payload

**Step 3: Add the CLI wrapper**

Create `scripts/demo/evaluate_nanobragg_accumulation.py` as a thin entrypoint over `orchestrator.demo.evaluators.nanobragg_accumulation:main`.

**Step 4: Run the evaluator tests and a manual CLI smoke check**

Run:
```bash
pytest tests/test_demo_nanobragg_evaluator.py -q
python scripts/demo/evaluate_nanobragg_accumulation.py examples/demo_task_nanobragg_accumulation_port
```

Expected:
- the pytest suite PASSes
- the CLI prints valid JSON
- the seed itself probably FAILs hidden acceptance because the visible module is still a skeleton; that is acceptable at this stage

**Step 5: Commit the evaluator implementation**

```bash
git add orchestrator/demo/evaluators/nanobragg_accumulation.py \
  orchestrator/demo/evaluators/__init__.py \
  scripts/demo/evaluate_nanobragg_accumulation.py
git commit -m "feat: add nanoBragg hidden evaluator"
```

### Task 4: Add a smoke test that the evaluator does not mutate the workspace

**Files:**
- Create: `tests/test_demo_nanobragg_evaluator_smoke.py`
- Read: `tests/test_demo_trial_smoke.py`
- Read: `tests/demo_helpers.py`

**Step 1: Write a failing smoke test**

Create a smoke test that:
- provisions a temporary workspace from `examples/demo_task_nanobragg_accumulation_port`
- runs `evaluate_workspace(...)` against one workspace copy
- asserts the evaluator returns the expected JSON shape
- asserts the visible workspace tree is unchanged before vs after evaluation

Use a file-tree snapshot helper rather than a real git diff.

**Step 2: Run the smoke test to verify it fails**

Run:
```bash
pytest tests/test_demo_nanobragg_evaluator_smoke.py -q
```

Expected:
- FAIL until the evaluator helper paths and fixture loading are stable.

**Step 3: Implement the smallest evaluator changes needed to make the smoke test pass**

Do not widen the evaluator surface area. Fix only:
- workspace import isolation
- fixture path resolution
- accidental writes into the workspace

**Step 4: Run the focused evaluator suite**

Run:
```bash
pytest tests/test_demo_nanobragg_evaluator.py tests/test_demo_nanobragg_evaluator_smoke.py -q
```

Expected:
- PASS.

**Step 5: Commit the smoke coverage**

```bash
git add tests/test_demo_nanobragg_evaluator_smoke.py tests/demo_helpers.py
git commit -m "test: add nanoBragg evaluator smoke coverage"
```
