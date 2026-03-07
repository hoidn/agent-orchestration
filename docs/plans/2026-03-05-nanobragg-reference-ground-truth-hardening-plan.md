# nanoBragg Reference Ground Truth Hardening Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the synthetic hidden nanoBragg evaluator corpus with real reference tensors derived from the scoped `nanoBragg.c` accumulation subsystem, so the hidden evaluator measures actual parity instead of arbitrary targets.

**Architecture:** Keep the existing hidden evaluator shape, but replace the corpus builder with an offline reference-generation pipeline. Build a narrow reference harness around the scoped C subsystem, generate expected tensors and trace taps from the visible JSON fixtures, and store only the resulting hidden artifacts in the main repo. Do not run the C harness during demo trials; use it only as a maintenance tool for regenerating hidden ground truth.

**Tech Stack:** Python 3.11+, PyTorch, pytest, C compilation via `cc`/`clang`/`gcc`, JSON fixtures, repo-local scripts under `scripts/demo/`, hidden evaluator assets under `orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/`.

---

### Task 1: Freeze the reference-data contract and expose that the current corpus is synthetic

**Files:**
- Modify: `orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/README.md`
- Modify: `orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/cases.json`
- Modify: `scripts/demo/build_nanobragg_reference_cases.py`
- Test: `tests/test_demo_nanobragg_evaluator.py`

**Step 1: Write the failing tests for provenance-aware hidden cases**

Extend `tests/test_demo_nanobragg_evaluator.py` so it asserts:
- each hidden case includes provenance metadata
- each case records the reference source identity
- the corpus builder is no longer allowed to depend on hard-coded tensors in Python source

Minimum expected metadata fields in each case:
- `case_id`
- `input_fixture_relpath`
- `expected_tensor_relpath`
- `rtol`
- `atol`
- `reference_method`
- `reference_source`
- `reference_commit` or `reference_snapshot`
- optional `trace_taps`

**Step 2: Run the focused test to verify it fails**

Run:
```bash
pytest tests/test_demo_nanobragg_evaluator.py -q
```

Expected:
- FAIL because the current corpus metadata and builder still describe or imply synthetic tensors.

**Step 3: Update the corpus README and metadata schema**

Revise the hidden corpus README so it explicitly distinguishes:
- visible fixture inputs
- hidden expected outputs
- reference provenance
- regeneration workflow

Update `cases.json` to include placeholder provenance fields for each case.

**Step 4: Remove the hard-coded `REFERENCE_TENSORS` pattern from the builder**

Change `scripts/demo/build_nanobragg_reference_cases.py` so it fails fast with a clear message until a real reference backend is implemented. Do not leave the synthetic tensor map in place.

**Step 5: Run the focused test again**

Run:
```bash
pytest tests/test_demo_nanobragg_evaluator.py -q
```

Expected:
- still FAIL overall because the real backend does not exist yet
- but the failure should now reflect missing reference-generation implementation, not synthetic constants.

**Step 6: Commit**

```bash
git add \
  orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/README.md \
  orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/cases.json \
  scripts/demo/build_nanobragg_reference_cases.py \
  tests/test_demo_nanobragg_evaluator.py
git commit -m "test: define nanoBragg reference provenance contract"
```

### Task 2: Add a narrow extracted C reference harness for the scoped subsystem

**Files:**
- Create: `scripts/demo/nanobragg_reference/extract_accumulation_slice.py`
- Create: `scripts/demo/nanobragg_reference/reference_types.h`
- Create: `scripts/demo/nanobragg_reference/reference_harness.c`
- Create: `scripts/demo/nanobragg_reference/README.md`
- Read: `../nanoBragg/golden_suite_generator/nanoBragg.c`
- Read: `examples/demo_task_nanobragg_accumulation_port/src_c/README.md`
- Test: `tests/test_demo_nanobragg_reference_harness.py`

**Step 1: Write the failing harness-contract tests**

Create `tests/test_demo_nanobragg_reference_harness.py` covering:
- the harness files exist
- the extraction script produces a bounded slice or validates line anchors
- the harness CLI can be invoked in a dry-run/compile-check mode
- the harness does not depend on the full demo seed layout at runtime

Keep this test file local to the maintenance toolchain. It should not invoke the trial runner.

**Step 2: Run the new test to verify it fails**

Run:
```bash
pytest tests/test_demo_nanobragg_reference_harness.py -q
```

Expected:
- FAIL because the reference harness files do not exist yet.

**Step 3: Implement the extraction and harness scaffold**

Add:
- `extract_accumulation_slice.py` to document and verify the exact scoped region in `nanoBragg.c`
- `reference_types.h` for the minimal input structs needed by the harness
- `reference_harness.c` implementing a narrow translation boundary:
  - load a structured JSON case
  - populate only the scoped inputs required by the accumulation slice
  - execute the reference accumulation path
  - emit detector image tensor data and optional trace taps as JSON or binary

Do not try to compile the entire original `nanoBragg.c` program. The harness should be a maintenance-oriented reference wrapper around the scoped math only.

**Step 4: Add a README with exact assumptions**

Document:
- source file path used
- exact scoped lines or anchor comments
- omitted factors and how they are normalized
- build command
- regeneration command
- why this harness is offline-only and not part of trial runtime

**Step 5: Run the harness-contract tests**

Run:
```bash
pytest tests/test_demo_nanobragg_reference_harness.py -q
```

Expected:
- PASS.

**Step 6: Commit**

```bash
git add \
  scripts/demo/nanobragg_reference \
  tests/test_demo_nanobragg_reference_harness.py
git commit -m "feat: add nanoBragg reference harness scaffold"
```

### Task 3: Make the reference harness executable on visible fixtures

**Files:**
- Modify: `scripts/demo/nanobragg_reference/reference_harness.c`
- Modify: `scripts/demo/nanobragg_reference/README.md`
- Modify: `scripts/demo/build_nanobragg_reference_cases.py`
- Create: `scripts/demo/nanobragg_reference/run_reference_case.py`
- Test: `tests/test_demo_nanobragg_reference_generation.py`

**Step 1: Write the failing reference-generation tests**

Create `tests/test_demo_nanobragg_reference_generation.py` that:
- builds or invokes the harness backend for one visible fixture
- asserts it returns an output tensor with the declared shape
- asserts the builder can consume the reference output and write a `.pt` file
- asserts provenance fields are populated in the output metadata

Use one visible case first, not the full corpus.

**Step 2: Run the test to verify it fails**

Run:
```bash
pytest tests/test_demo_nanobragg_reference_generation.py -q
```

Expected:
- FAIL because the harness is not yet executable end-to-end.

**Step 3: Implement `run_reference_case.py`**

Add a thin script that:
- takes a visible JSON fixture path
- builds the harness if needed
- invokes the harness on that fixture
- writes a structured temporary result containing:
  - detector tensor values
  - dtype and shape
  - optional trace taps
  - provenance fields

**Step 4: Implement real reference-case generation in the builder**

Replace the current builder body with logic that:
- reads `cases.json`
- for each case, runs the harness on the corresponding visible input fixture
- stores the emitted tensor as the hidden expected `.pt`
- records or verifies provenance metadata

Do not leave any hard-coded expected arrays in the repo.

**Step 5: Run the single-case generation test**

Run:
```bash
pytest tests/test_demo_nanobragg_reference_generation.py -q
```

Expected:
- PASS.

**Step 6: Commit**

```bash
git add \
  scripts/demo/build_nanobragg_reference_cases.py \
  scripts/demo/nanobragg_reference/run_reference_case.py \
  scripts/demo/nanobragg_reference/reference_harness.c \
  scripts/demo/nanobragg_reference/README.md \
  tests/test_demo_nanobragg_reference_generation.py
git commit -m "feat: generate nanoBragg reference tensors from C harness"
```

### Task 4: Regenerate the hidden corpus from the real C reference

**Files:**
- Modify: `orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/expected_case_small.pt`
- Modify: `orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/expected_case_thickness.pt`
- Modify: `orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/expected_case_mosaic.pt`
- Modify: `orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/cases.json`
- Test: `tests/test_demo_nanobragg_evaluator.py`
- Test: `tests/test_demo_nanobragg_evaluator_smoke.py`

**Step 1: Run the real builder**

Run:
```bash
python scripts/demo/build_nanobragg_reference_cases.py
```

Expected:
- three `.pt` tensors are regenerated from the reference harness
- output logs identify the fixture source and reference provenance

**Step 2: Re-run the evaluator tests**

Run:
```bash
pytest tests/test_demo_nanobragg_evaluator.py tests/test_demo_nanobragg_evaluator_smoke.py -q
```

Expected:
- PASS.

**Step 3: Inspect the generated hidden tensors**

Run:
```bash
python - <<'PY'
from pathlib import Path
import torch
root = Path('orchestrator/demo/evaluators/fixtures/nanobragg_accumulation')
for name in ['expected_case_small.pt', 'expected_case_thickness.pt', 'expected_case_mosaic.pt']:
    tensor = torch.load(root / name, map_location='cpu')
    print(name, tensor.shape, tensor.dtype, float(tensor.min()), float(tensor.max()))
PY
```

Expected:
- shapes match the visible fixtures
- values are finite
- values are no longer the obvious synthetic constants from the current corpus

**Step 4: Commit**

```bash
git add orchestrator/demo/evaluators/fixtures/nanobragg_accumulation
git commit -m "feat: replace synthetic nanoBragg hidden corpus with C-derived reference"
```

### Task 5: Add trace-tap debugging and evaluator provenance reporting

**Files:**
- Modify: `orchestrator/demo/evaluators/nanobragg_accumulation.py`
- Modify: `orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/cases.json`
- Modify: `orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/README.md`
- Test: `tests/test_demo_nanobragg_evaluator.py`

**Step 1: Write the failing trace/provenance tests**

Extend `tests/test_demo_nanobragg_evaluator.py` so it asserts:
- failure payloads include provenance information
- if `trace_taps` are declared, the evaluator reports which case failed and which tap locations were relevant

Keep this lightweight. Do not add a large new result schema.

**Step 2: Run the test to verify it fails**

Run:
```bash
pytest tests/test_demo_nanobragg_evaluator.py -q
```

Expected:
- FAIL until the evaluator exposes the extra fields.

**Step 3: Implement evaluator reporting improvements**

Update the evaluator so failed cases include:
- reference source
- reference snapshot/commit
- tap coordinates from the case metadata

Do not dump entire tensors into the JSON result.

**Step 4: Run the focused tests**

Run:
```bash
pytest tests/test_demo_nanobragg_evaluator.py tests/test_demo_nanobragg_evaluator_smoke.py -q
```

Expected:
- PASS.

**Step 5: Commit**

```bash
git add \
  orchestrator/demo/evaluators/nanobragg_accumulation.py \
  orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/cases.json \
  orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/README.md \
  tests/test_demo_nanobragg_evaluator.py
git commit -m "feat: add nanoBragg evaluator provenance reporting"
```

### Task 6: Re-run the flagship comparison and document the evaluator quality level

**Files:**
- Modify: `docs/plans/2026-03-05-workflow-demo-session-handoff.md`
- Modify: `docs/plans/2026-03-05-demo-scaffold-and-runbook.md`
- Modify: `docs/plans/2026-03-05-nanobragg-hidden-evaluator-implementation-plan.md`
- Test: `tests/test_demo_nanobragg_trial_smoke.py`

**Step 1: Run the nanoBragg trial smoke coverage**

Run:
```bash
pytest tests/test_demo_nanobragg_trial_smoke.py tests/test_demo_trial_runner.py tests/test_demo_trial_runner_observability.py -q
```

Expected:
- PASS.

**Step 2: Run one fresh real direct/workflow trial**

Run:
```bash
python scripts/demo/run_trial.py \
  --seed-repo examples/demo_task_nanobragg_accumulation_port \
  --experiment-root /tmp/nanobragg-reference-hardened-trial \
  --task-file examples/demo_task_nanobragg_accumulation_port/docs/tasks/port_nanobragg_accumulation_to_pytorch.md
```

If `run_trial.py` still has the non-empty experiment-root bug or git-seed limitation, use the documented manual provisioning workaround, but document that explicitly.

**Step 3: Update the runbook and handoff**

Revise the docs so they no longer describe the hidden evaluator as merely stronger-than-visible. They should state:
- the corpus is derived from a real C reference harness
- the exact provenance fields carried in `cases.json`
- any remaining limitations

**Step 4: Commit**

```bash
git add \
  docs/plans/2026-03-05-workflow-demo-session-handoff.md \
  docs/plans/2026-03-05-demo-scaffold-and-runbook.md \
  docs/plans/2026-03-05-nanobragg-hidden-evaluator-implementation-plan.md
git commit -m "docs: record hardened nanoBragg reference evaluator"
```

### Task 7: Add an explicit guard against regressing back to synthetic tensors

**Files:**
- Create: `tests/test_demo_nanobragg_reference_provenance.py`
- Read: `scripts/demo/build_nanobragg_reference_cases.py`
- Read: `orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/cases.json`

**Step 1: Write the failing regression test**

Add a test that fails if:
- the builder source contains a literal reference-tensor lookup table
- the corpus metadata is missing provenance fields
- the expected tensors are regenerated without the reference harness path being involved

This is a policy test against quietly slipping back into fake ground truth.

**Step 2: Run the test to verify it fails if the guard is not yet enforced**

Run:
```bash
pytest tests/test_demo_nanobragg_reference_provenance.py -q
```

Expected:
- PASS only once the builder and metadata fully reflect the reference-harness design.

**Step 3: Commit**

```bash
git add tests/test_demo_nanobragg_reference_provenance.py
git commit -m "test: guard nanoBragg reference corpus provenance"
```

---

## Notes for the implementer

- The current hidden evaluator is structurally useful but not trustworthy as ground truth. Do not preserve the synthetic tensor generation path “for convenience.”
- Keep the visible demo seed unchanged where possible. The reference harness belongs in the main repo maintenance toolchain, not in the candidate workspace.
- Prefer a narrow extracted subsystem harness over trying to compile and drive the full `nanoBragg.c` program.
- If the scoped C math cannot be isolated cleanly enough, stop and document the blocker instead of backsliding into arbitrary reference tensors.

Plan complete and saved to `docs/plans/2026-03-05-nanobragg-reference-ground-truth-hardening-plan.md`. Two execution options:

1. Subagent-Driven (this session) - I dispatch fresh subagent per task, review between tasks, fast iteration
2. Parallel Session (separate) - Open new session with `executing-plans`, batch execution with checkpoints

Which approach?
