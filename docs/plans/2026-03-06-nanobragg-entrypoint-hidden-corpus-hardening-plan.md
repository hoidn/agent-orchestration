# nanoBragg Entrypoint Hidden Corpus Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the weak 3-case visible-fixture-backed hidden evaluator corpus with a larger hidden-only scored corpus that better discriminates partial or overfit `nanobragg_run` ports.

**Architecture:** Keep the public task thin and unchanged, but move hidden evaluation onto a generated hidden fixture bank under the evaluator fixture root. The builder will generate many reference-backed input/output pairs, and the evaluator will score candidate outputs across the whole hidden bank instead of only the visible smoke inputs.

**Tech Stack:** Python 3, PyTorch, pytest, existing C reference harness.

---

## Task 1: Write failing tests for a stronger hidden corpus

**Files:**
- Modify: `tests/test_demo_nanobragg_entrypoint_fixture_schema.py`
- Modify: `tests/test_demo_nanobragg_entrypoint_evaluator.py`
- Modify: `tests/test_demo_nanobragg_entrypoint_evaluator_smoke.py`

**Step 1: Require hidden-only cases and a larger corpus**
- Assert hidden manifest contains at least 10 cases.
- Assert at least 5 cases are hidden-only inputs stored under evaluator fixtures, not under `fixtures/visible/`.
- Assert hidden cases cover at least 2 output shapes.

**Step 2: Require evaluator to execute hidden-only cases**
- Update evaluator tests so a candidate that only matches one visible case cannot pass.
- Add a test that inspects `executed_cases` and verifies hidden-only case ids are included.

**Step 3: Run focused tests to verify RED**
Run:
```bash
pytest -q tests/test_demo_nanobragg_entrypoint_fixture_schema.py tests/test_demo_nanobragg_entrypoint_evaluator.py tests/test_demo_nanobragg_entrypoint_evaluator_smoke.py
```
Expected:
- FAIL because corpus is still only 3 visible-backed cases.

**Step 4: Run collect-only after test edits**
Run:
```bash
pytest --collect-only -q tests/test_demo_nanobragg_entrypoint_fixture_schema.py tests/test_demo_nanobragg_entrypoint_evaluator.py tests/test_demo_nanobragg_entrypoint_evaluator_smoke.py
```
Expected:
- collection succeeds.

**Step 5: Commit**
```bash
git add tests/test_demo_nanobragg_entrypoint_fixture_schema.py tests/test_demo_nanobragg_entrypoint_evaluator.py tests/test_demo_nanobragg_entrypoint_evaluator_smoke.py
git commit -m "test: require stronger nanobragg hidden corpus"
```

## Task 2: Expand the builder to generate a real hidden corpus

**Files:**
- Modify: `scripts/demo/build_nanobragg_entrypoint_cases.py`
- Modify: `orchestrator/demo/evaluators/fixtures/nanobragg_entrypoint/README.md`

**Step 1: Split public visible cases from hidden evaluation cases**
- Keep visible fixtures as the current 3 smoke cases.
- Add a larger internal `HIDDEN_CASES` list in the builder with at least 10 total cases.
- Include at least 5 hidden-only cases written under `orchestrator/demo/evaluators/fixtures/nanobragg_entrypoint/inputs/`.

**Step 2: Vary meaningful dimensions without exploding runtime**
Include cases covering:
- multiple detector shapes (for example `4x4`, `3x5`, `5x6`)
- thickness on/off and varied thickness-step settings
- mosaic on/off and varied mosaic domains / phi settings
- varied `N` / cell parameters / distance / pixel / lambda where supported by the entrypoint path

**Step 3: Preserve task fairness**
- Hidden inputs must use the same fixture schema as visible fixtures.
- Do not add hidden-only bespoke fields.
- Keep case ids and input files opaque to the public task.

**Step 4: Regenerate expected tensors from the C harness**
- Write hidden-only input fixtures under the evaluator fixture root.
- Regenerate `.pt` expected outputs and `cases.json` from the reference harness.

**Step 5: Commit**
```bash
git add scripts/demo/build_nanobragg_entrypoint_cases.py orchestrator/demo/evaluators/fixtures/nanobragg_entrypoint

git commit -m "feat: expand nanobragg hidden evaluator corpus"
```

## Task 3: Update the evaluator to consume hidden-only inputs cleanly

**Files:**
- Modify: `orchestrator/demo/evaluators/nanobragg_entrypoint.py`

**Step 1: Decouple hidden inputs from the candidate workspace**
- For each case, load fixture input from either:
  - evaluator fixture root (hidden-only inputs), or
  - workspace visible fixture path for public smoke-backed cases if retained.
- Prefer evaluator-owned hidden input paths in the manifest.

**Step 2: Keep score-first behavior**
- Preserve case-level component scores and aggregate mean score.
- Keep `verdict` as thresholded derivative for runner compatibility.

**Step 3: Keep probes natural**
- Score only output-space observables and selected output probe sites.
- Do not require decomposition-specific instrumentation.

**Step 4: Commit**
```bash
git add orchestrator/demo/evaluators/nanobragg_entrypoint.py
git commit -m "feat: evaluate nanobragg entrypoint on hidden-only corpus"
```

## Task 4: Regenerate fixtures and verify green

**Files:**
- Regenerate: `orchestrator/demo/evaluators/fixtures/nanobragg_entrypoint/cases.json`
- Regenerate: `orchestrator/demo/evaluators/fixtures/nanobragg_entrypoint/expected_*.pt`
- Create: `orchestrator/demo/evaluators/fixtures/nanobragg_entrypoint/inputs/*.json`

**Step 1: Rebuild the hidden corpus**
Run:
```bash
python scripts/demo/build_nanobragg_entrypoint_cases.py
```
Expected:
- hidden input fixtures exist under `.../inputs/`
- manifest references many cases
- expected tensors regenerate cleanly

**Step 2: Run focused tests**
Run:
```bash
pytest -q tests/test_demo_nanobragg_entrypoint_fixture_schema.py tests/test_demo_nanobragg_entrypoint_evaluator.py tests/test_demo_nanobragg_entrypoint_evaluator_smoke.py
```
Expected:
- PASS

**Step 3: Re-run collect-only**
Run:
```bash
pytest --collect-only -q tests/test_demo_nanobragg_entrypoint_fixture_schema.py tests/test_demo_nanobragg_entrypoint_evaluator.py tests/test_demo_nanobragg_entrypoint_evaluator_smoke.py
```
Expected:
- collection succeeds.

## Task 5: Rerun a demo-smoke-relevant verification

**Files:**
- No code changes required unless runner assumptions break.

**Step 1: Run a demo smoke check touching the entrypoint evaluator path**
Run:
```bash
pytest -q tests/test_demo_trial_runner.py -k nanobragg
```
If selector matches nothing, run:
```bash
pytest -q tests/test_demo_trial_runner.py
```
Expected:
- PASS

**Step 2: Summarize the new benchmark strength**
Record:
- number of hidden cases
- number of hidden-only cases
- output shapes covered
- scoring behavior retained

**Step 3: Commit**
```bash
git add docs/plans/2026-03-06-nanobragg-entrypoint-hidden-corpus-hardening-plan.md
git commit -m "docs: add nanobragg hidden corpus hardening plan"
```
