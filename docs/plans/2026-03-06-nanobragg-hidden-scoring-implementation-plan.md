# nanoBragg Hidden Scoring Implementation Plan

**Goal:** Replace the new nanoBragg entrypoint hidden evaluator's binary-only judgment with a score-first model based on multiple hidden cases, probe sites, and output conditions.

**Architecture:** Keep the hidden evaluator harness-backed and deterministic, but change the evaluator contract so each hidden case yields a weighted score from several conditions. Preserve `verdict` only as a thresholded derivative of the score for compatibility with the current trial runner.

**Constraint:** Hidden probe sites must be chosen from naturally measurable observables and stable semantics at the task boundary. If a probe would require task-specific debug plumbing, a solution-shaped public API, or one preferred internal decomposition, change the task boundary or the hidden scoring design instead of exposing more implementation guidance.

**Tech Stack:** Python case builder, hidden fixture metadata, PyTorch evaluator, pytest.

---

### Task 1: Define The Scoring Contract

**Files:**
- Create: `docs/plans/2026-03-06-nanobragg-hidden-scoring-implementation-plan.md`
- Modify: `orchestrator/demo/evaluators/fixtures/nanobragg_entrypoint/cases.json`
- Modify: `scripts/demo/build_nanobragg_entrypoint_cases.py`

**Steps:**
1. Add hidden `probe_sites` metadata per case so the evaluator has explicit hidden test points.
   - restrict probes to natural output-space locations or semantically stable intermediate quantities implied by the entrypoint contract itself
2. Define the per-case score as a weighted combination of:
   - shape correctness
   - dtype correctness
   - finiteness
   - probe-site closeness
   - full-tensor closeness
3. Keep the overall trial-facing verdict as a thresholded derivative of the aggregate score, not the primary output.

### Task 2: Implement Score-Based Evaluation

**Files:**
- Modify: `orchestrator/demo/evaluators/nanobragg_entrypoint.py`
- Modify: `scripts/demo/evaluate_nanobragg_entrypoint.py`

**Steps:**
1. Compute a per-case score and emit a structured per-case breakdown.
2. Aggregate scores across executed hidden cases into one normalized overall score.
3. Preserve `verdict` for compatibility, but make it secondary to the score.
4. Ensure evaluator output still works with the current runner archive format.
5. Do not require the candidate implementation to expose bespoke hidden-test instrumentation hooks or any specific internal decomposition.

### Task 3: Update Tests

**Files:**
- Modify: `tests/test_demo_nanobragg_entrypoint_fixture_schema.py`
- Modify: `tests/test_demo_nanobragg_entrypoint_evaluator.py`
- Modify: `tests/test_demo_nanobragg_entrypoint_evaluator_smoke.py`

**Steps:**
1. Require `probe_sites` in hidden case metadata.
2. Require evaluator results to include an overall score.
3. Update smoke expectations so the current stub seed fails with a low score rather than only a binary failure.

### Task 4: Verify End-To-End

**Checks:**
```bash
python scripts/demo/build_nanobragg_entrypoint_cases.py
pytest tests/test_demo_nanobragg_entrypoint_fixture_schema.py tests/test_demo_nanobragg_entrypoint_evaluator.py tests/test_demo_nanobragg_entrypoint_evaluator_smoke.py -q
pytest --collect-only -q tests/test_demo_nanobragg_entrypoint_fixture_schema.py tests/test_demo_nanobragg_entrypoint_evaluator.py tests/test_demo_nanobragg_entrypoint_evaluator_smoke.py
```

**Exit Criteria:**
- hidden case metadata includes probe sites
- evaluator emits score plus per-case breakdown
- the current stub seed produces a non-passing score
- passing fixtures still score `1.0`
