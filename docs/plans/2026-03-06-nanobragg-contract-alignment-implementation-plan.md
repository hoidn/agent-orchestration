# nanoBragg Contract Alignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the nanoBragg demo task, visible verification, workflow review criteria, and hidden evaluator all target the same scoped mathematical contract so direct-vs-workflow outcomes are fair and interpretable.

**Architecture:** Treat the offline reference harness as the current executable source of truth and narrow the visible task/seed around that exact scoped model. Add an explicit contract document that defines included math, excluded math, normalization rules, oversampling semantics, and restructuring constraints; then derive visible task text, visible tests, and maintenance checks from that contract. Do not broaden the hidden harness in this pass.

**Tech Stack:** Markdown task/spec docs, pytest maintenance tests, existing nanoBragg seed under `examples/demo_task_nanobragg_accumulation_port/`, hidden evaluator fixtures under `orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/`, offline C reference harness under `scripts/demo/nanobragg_reference/`.

---

### Task 1: Freeze the scoped mathematical contract in one authoritative doc

**Files:**
- Create: `examples/demo_task_nanobragg_accumulation_port/docs/tasks/nanobragg_accumulation_contract.md`
- Read: `scripts/demo/nanobragg_reference/reference_harness.c`
- Read: `scripts/demo/nanobragg_reference/run_reference_case.py`
- Read: `examples/demo_task_nanobragg_accumulation_port/src_c/README.md`
- Test: `tests/test_demo_task_nanobragg_contract.py`

**Step 1: Write the failing contract-presence test**

Create `tests/test_demo_task_nanobragg_contract.py` asserting:
- `nanobragg_accumulation_contract.md` exists
- it contains sections for:
  - included math
  - excluded math
  - input contract
  - normalization rules
  - oversample semantics
  - restructuring constraints
- it explicitly states whether source directions, phi values, mosaic domains, polarization, scattering vectors, and lattice factors are in or out of scope

**Step 2: Run the test to verify it fails**

Run:
```bash
pytest tests/test_demo_task_nanobragg_contract.py -q
```

Expected:
- FAIL because the contract doc does not exist yet.

**Step 3: Write the contract doc from the reference harness**

Document the current scoped model exactly as implemented in `reference_harness.c`:
- included math:
  - detector/subpixel coordinate construction
  - `omega_pixel`
  - `capture_fraction`
  - source weights
  - mosaic weights
  - accumulation over source / phi / mosaic counts
  - post-loop application of `capture_fraction` and `omega_pixel` when the corresponding oversample flags are false
- excluded math:
  - scattering-vector construction
  - polarization factor
  - lattice/unit-cell/structure-factor terms beyond the explicit scoped defaults
  - any richer physical model not present in the harness
- normalization:
  - divide only by `subpixel_steps * subpixel_steps`
  - do not divide by thickness steps
- oversample semantics:
  - match the harness exactly for `oversample_omega` and `oversample_thick`
- restructuring constraints:
  - detector/subpixel axes must be tensorized
  - residual loops only where contract allows them

**Step 4: Run the test again**

Run:
```bash
pytest tests/test_demo_task_nanobragg_contract.py -q
```

Expected:
- PASS.

**Step 5: Commit**

```bash
git add \
  examples/demo_task_nanobragg_accumulation_port/docs/tasks/nanobragg_accumulation_contract.md \
  tests/test_demo_task_nanobragg_contract.py
git commit -m "docs: define nanobragg scoped contract"
```

### Task 2: Rewrite the user-facing task and higher-level spec to point at the contract

**Files:**
- Modify: `examples/demo_task_nanobragg_accumulation_port/docs/tasks/port_nanobragg_accumulation_to_pytorch.md`
- Modify: `docs/plans/2026-03-05-nanobragg-subsystem-task-spec.md`
- Modify: `examples/demo_task_nanobragg_accumulation_port/docs/index.md`
- Test: `tests/test_demo_task_nanobragg_contract.py`

**Step 1: Extend the failing test with alignment assertions**

Add assertions that the task markdown:
- references `nanobragg_accumulation_contract.md` as the authoritative behavior definition
- does not require physics terms that the contract marks out of scope
- states that restructuring must preserve the scoped contract, not a broader interpretation of `nanoBragg.c`

Add assertions that the higher-level spec:
- distinguishes the original aspirational slice from the now-authoritative demo contract
- clearly states this demo task uses the narrower scoped harness-backed model

**Step 2: Run the test to verify it fails**

Run:
```bash
pytest tests/test_demo_task_nanobragg_contract.py -q
```

Expected:
- FAIL because the task/spec still mention scattering, polarization, and lattice-related factors as required behavior.

**Step 3: Rewrite the task text**

Update `port_nanobragg_accumulation_to_pytorch.md` so it:
- points to `nanobragg_accumulation_contract.md` as the source of truth
- says the task is to implement the contract faithfully while restructuring loops into tensors
- removes or demotes broader “real nanoBragg-like” language
- explicitly says not to add out-of-contract physics/model terms

**Step 4: Rewrite the subsystem spec**

Update `2026-03-05-nanobragg-subsystem-task-spec.md` so it:
- records that the initial broader subsystem concept has been narrowed for demo fairness
- describes this narrowed contract as the current flagship task
- leaves broader-harness expansion as future work, not current acceptance criteria

**Step 5: Update the seed index doc**

Add a short note in the seed `docs/index.md` directing agents to the contract doc for exact mathematical scope.

**Step 6: Run the test again**

Run:
```bash
pytest tests/test_demo_task_nanobragg_contract.py -q
```

Expected:
- PASS.

**Step 7: Commit**

```bash
git add \
  examples/demo_task_nanobragg_accumulation_port/docs/tasks/port_nanobragg_accumulation_to_pytorch.md \
  examples/demo_task_nanobragg_accumulation_port/docs/tasks/nanobragg_accumulation_contract.md \
  examples/demo_task_nanobragg_accumulation_port/docs/index.md \
  docs/plans/2026-03-05-nanobragg-subsystem-task-spec.md \
  tests/test_demo_task_nanobragg_contract.py
git commit -m "docs: align nanobragg task with scoped contract"
```

### Task 3: Align the visible seed tests and guidance with the scoped contract

**Files:**
- Modify: `examples/demo_task_nanobragg_accumulation_port/tests/test_smoke_accumulation.py`
- Modify: `examples/demo_task_nanobragg_accumulation_port/fixtures/visible/README.md`
- Modify: `examples/demo_task_nanobragg_accumulation_port/src_c/README.md`
- Create: `tests/test_demo_task_nanobragg_visible_contract.py`

**Step 1: Write the failing visible-contract test**

Create `tests/test_demo_task_nanobragg_visible_contract.py` asserting:
- visible fixture README points at the scoped contract doc
- source README describes the scoped harness-backed behavior rather than a richer subsystem promise
- smoke tests do not imply coverage of out-of-contract physics terms

**Step 2: Run the test to verify it fails**

Run:
```bash
pytest tests/test_demo_task_nanobragg_visible_contract.py -q
```

Expected:
- FAIL because the visible docs still describe a broader subsystem.

**Step 3: Update visible docs and smoke comments**

Revise visible seed docs so they say:
- smoke tests are contract smoke checks, not full nanoBragg parity
- visible fixtures are authoritative only for the scoped contract
- the source slice is included for context, but the contract doc controls scope

Keep `tests/test_smoke_accumulation.py` lightweight, but remove wording that suggests it covers broader scattering/polarization/lattice behavior if it does not.

**Step 4: Run the test again**

Run:
```bash
pytest tests/test_demo_task_nanobragg_visible_contract.py -q
```

Expected:
- PASS.

**Step 5: Commit**

```bash
git add \
  examples/demo_task_nanobragg_accumulation_port/tests/test_smoke_accumulation.py \
  examples/demo_task_nanobragg_accumulation_port/fixtures/visible/README.md \
  examples/demo_task_nanobragg_accumulation_port/src_c/README.md \
  tests/test_demo_task_nanobragg_visible_contract.py
git commit -m "docs: align nanobragg visible seed guidance"
```

### Task 4: Add a maintenance test that task/spec and evaluator remain aligned

**Files:**
- Create: `tests/test_demo_task_nanobragg_alignment.py`
- Read: `orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/README.md`
- Read: `orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/cases.json`
- Read: `scripts/demo/nanobragg_reference/reference_harness.c`

**Step 1: Write the failing alignment test**

Create a maintenance test that:
- reads `nanobragg_accumulation_contract.md`
- reads the task markdown
- reads the evaluator README/case metadata
- asserts the same included/excluded concept set appears across all of them

At minimum, assert agreement on whether the demo contract includes:
- `omega_pixel`
- `capture_fraction`
- source weights
- phi count iteration
- mosaic weights
- scattering vectors
- polarization
- lattice/structure factors
- normalization by thickness steps

**Step 2: Run the test to verify it fails or is missing coverage**

Run:
```bash
pytest tests/test_demo_task_nanobragg_alignment.py -q
```

Expected:
- FAIL initially unless every artifact is already aligned.

**Step 3: Implement the minimum metadata/doc updates to satisfy the test**

Update evaluator README and/or contract wording so the alignment test passes without changing the hidden harness behavior.

Do not broaden the hidden harness in this task.

**Step 4: Run the test again**

Run:
```bash
pytest tests/test_demo_task_nanobragg_alignment.py -q
```

Expected:
- PASS.

**Step 5: Commit**

```bash
git add \
  tests/test_demo_task_nanobragg_alignment.py \
  orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/README.md \
  orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/cases.json \
  examples/demo_task_nanobragg_accumulation_port/docs/tasks/nanobragg_accumulation_contract.md \
  examples/demo_task_nanobragg_accumulation_port/docs/tasks/port_nanobragg_accumulation_to_pytorch.md
git commit -m "test: enforce nanobragg contract alignment"
```

### Task 5: Update workflow-facing documentation to review against the scoped contract

**Files:**
- Modify: `docs/plans/2026-03-05-workflow-demo-session-handoff.md`
- Modify: `docs/plans/2026-03-05-workflow-demo-design.md`
- Modify: `prompts/workflows/generic_task_loop/review_plan.md`
- Modify: `prompts/workflows/generic_task_loop/review_implementation.md`
- Test: `tests/test_demo_task_nanobragg_alignment.py`

**Step 1: Write the failing prompt/doc expectation assertions**

Extend `tests/test_demo_task_nanobragg_alignment.py` or add a second test that asserts:
- review guidance tells reviewers to judge correctness against task-defined contract and visible artifacts, not broader inferred domain behavior
- docs describe the nanoBragg flagship task as contract-scoped

**Step 2: Run the test to verify it fails**

Run:
```bash
pytest tests/test_demo_task_nanobragg_alignment.py -q
```

Expected:
- FAIL if the docs/prompts still nudge reviewers toward over-broad domain inference.

**Step 3: Update workflow review prompts and docs**

Change review guidance so reviewers:
- reject missing behavior only when it is required by the task contract
- explicitly distinguish “out-of-contract improvement” from “blocking correctness issue”
- remain allowed to reject for inadequate verification, but only relative to the scoped contract

Update the handoff/design docs to say the flagship nanoBragg task is now contract-scoped to the offline harness.

**Step 4: Run the test again**

Run:
```bash
pytest tests/test_demo_task_nanobragg_alignment.py -q
```

Expected:
- PASS.

**Step 5: Commit**

```bash
git add \
  prompts/workflows/generic_task_loop/review_plan.md \
  prompts/workflows/generic_task_loop/review_implementation.md \
  docs/plans/2026-03-05-workflow-demo-session-handoff.md \
  docs/plans/2026-03-05-workflow-demo-design.md \
  tests/test_demo_task_nanobragg_alignment.py
git commit -m "docs: scope workflow review to nanobragg contract"
```

### Task 6: Reprovision and rerun one fresh direct-vs-workflow trial on the aligned contract

**Files:**
- Modify: `docs/plans/2026-03-05-workflow-demo-session-handoff.md`
- Modify: `docs/plans/2026-03-05-demo-scaffold-and-runbook.md`
- Test/Run: fresh manual or scripted trial using `scripts/demo/provision_trial.py` and `scripts/demo/run_trial.py`

**Step 1: Run the contract and alignment tests first**

Run:
```bash
pytest \
  tests/test_demo_task_nanobragg_contract.py \
  tests/test_demo_task_nanobragg_visible_contract.py \
  tests/test_demo_task_nanobragg_alignment.py -q
```

Expected:
- PASS.

**Step 2: Provision a fresh trial from the aligned seed**

Use the current demo workflow and direct prompt setup, but ensure the provisioned workspaces come from the aligned seed/docs snapshot.

**Step 3: Launch one direct arm and one workflow arm**

Use the currently supported provider settings (for example Codex medium) and record:
- visible test result
- hidden evaluator result
- whether workflow review/fix behavior improved in a now-fair task environment

**Step 4: Update runbook and handoff**

Document:
- that the contract-alignment fix is in place
- that the narrowed contract is the current acceptance target
- any remaining gap after rerun

**Step 5: Run final verification commands**

Run:
```bash
pytest \
  tests/test_demo_task_nanobragg_contract.py \
  tests/test_demo_task_nanobragg_visible_contract.py \
  tests/test_demo_task_nanobragg_alignment.py \
  tests/test_demo_trial_runner.py \
  tests/test_demo_provisioning.py -q
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/generic_task_plan_execute_review_loop.yaml --dry-run
```

Expected:
- PASS.

**Step 6: Commit**

```bash
git add \
  docs/plans/2026-03-05-workflow-demo-session-handoff.md \
  docs/plans/2026-03-05-demo-scaffold-and-runbook.md
git commit -m "docs: record aligned nanobragg demo contract"
```
