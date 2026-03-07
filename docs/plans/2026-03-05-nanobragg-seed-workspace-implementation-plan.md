# nanoBragg Seed Workspace Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a new visible demo seed repo, `examples/demo_task_nanobragg_accumulation_port`, that scopes the nanoBragg detector pixel accumulation subsystem into a hard PyTorch porting task with shared scaffold files, bounded task text, visible smoke checks, and provisioner-compatible layout.

**Architecture:** Follow the existing demo-seed pattern used by `examples/demo_task_linear_classifier_port`, but swap the task domain to a PyTorch port of the bounded nanoBragg accumulation subsystem. Keep all hidden assets out of the visible seed. Assume the trial environment already has CPU PyTorch installed; the seed only needs to document that expectation and provide a visible `pytest` entrypoint.

**Tech Stack:** Python 3.11+, PyTorch (preinstalled in the trial environment), pytest, Markdown task docs, git worktrees, existing `provision_trial` workspace layout.

---

### Task 1: Add failing repo-level tests for the new nanoBragg seed shape

**Files:**
- Create: `tests/test_demo_task_nanobragg_seed.py`
- Read: `tests/test_demo_task_seed.py`
- Read: `examples/demo_task_linear_classifier_port/`
- Read: `docs/plans/2026-03-05-nanobragg-subsystem-task-spec.md`

**Step 1: Write the failing seed-shape tests**

Create `tests/test_demo_task_nanobragg_seed.py` with tests that assert the new seed contains:
- `examples/demo_task_nanobragg_accumulation_port/AGENTS.md`
- `examples/demo_task_nanobragg_accumulation_port/docs/index.md`
- `examples/demo_task_nanobragg_accumulation_port/docs/dev_guidelines.md`
- `examples/demo_task_nanobragg_accumulation_port/docs/tasks/port_nanobragg_accumulation_to_pytorch.md`
- `examples/demo_task_nanobragg_accumulation_port/src_c/nanoBragg.c`
- `examples/demo_task_nanobragg_accumulation_port/src_c/README.md`
- `examples/demo_task_nanobragg_accumulation_port/torch_port/__init__.py`
- `examples/demo_task_nanobragg_accumulation_port/torch_port/accumulation.py`
- `examples/demo_task_nanobragg_accumulation_port/torch_port/geometry.py`
- `examples/demo_task_nanobragg_accumulation_port/torch_port/types.py`
- `examples/demo_task_nanobragg_accumulation_port/tests/test_smoke_accumulation.py`
- `examples/demo_task_nanobragg_accumulation_port/fixtures/visible/case_small.json`
- `examples/demo_task_nanobragg_accumulation_port/fixtures/visible/README.md`

Add text assertions that the task file mentions:
- `nanoBragg.c`
- `PyTorch`
- `tensor-level numerical parity`
- `do not port the entire program`
- `visible smoke checks are incomplete`
- `state/task.md`

Add dependency-band assertions that the visible seed does not add:
- C build scripts
- CUDA requirements
- external services

**Step 2: Run the seed test to verify it fails**

Run:
```bash
pytest tests/test_demo_task_nanobragg_seed.py -q
```

Expected:
- FAIL because the new seed does not exist yet.

**Step 3: Keep the failure output in the plan log**

Append the failing command and traceback summary to:
- `docs/plans/2026-03-05-nanobragg-seed-workspace-implementation-log.md`

Use a short note only; do not start implementation yet.

**Step 4: Commit the failing test only**

```bash
git add tests/test_demo_task_nanobragg_seed.py
git commit -m "test: define nanoBragg seed shape"
```

### Task 2: Create the visible scaffold and task definition for the nanoBragg seed

**Files:**
- Create: `examples/demo_task_nanobragg_accumulation_port/AGENTS.md`
- Create: `examples/demo_task_nanobragg_accumulation_port/README.md`
- Create: `examples/demo_task_nanobragg_accumulation_port/docs/index.md`
- Create: `examples/demo_task_nanobragg_accumulation_port/docs/dev_guidelines.md`
- Create: `examples/demo_task_nanobragg_accumulation_port/docs/backlog/active/README.md`
- Create: `examples/demo_task_nanobragg_accumulation_port/docs/backlog/done/.gitkeep`
- Create: `examples/demo_task_nanobragg_accumulation_port/docs/plans/templates/artifact_contracts.md`
- Create: `examples/demo_task_nanobragg_accumulation_port/docs/plans/templates/check_plan_schema.md`
- Create: `examples/demo_task_nanobragg_accumulation_port/docs/plans/templates/plan_template.md`
- Create: `examples/demo_task_nanobragg_accumulation_port/docs/plans/templates/review_template.md`
- Create: `examples/demo_task_nanobragg_accumulation_port/docs/tasks/port_nanobragg_accumulation_to_pytorch.md`
- Create: `examples/demo_task_nanobragg_accumulation_port/artifacts/checks/.gitkeep`
- Create: `examples/demo_task_nanobragg_accumulation_port/artifacts/review/.gitkeep`
- Create: `examples/demo_task_nanobragg_accumulation_port/artifacts/work/.gitkeep`
- Create: `examples/demo_task_nanobragg_accumulation_port/state/.gitkeep`
- Read: `examples/demo_task_linear_classifier_port/AGENTS.md`
- Read: `examples/demo_task_linear_classifier_port/docs/index.md`
- Read: `docs/plans/2026-03-05-nanobragg-subsystem-task-spec.md`

**Step 1: Copy the shared scaffold pattern without copying the old task text**

Use the linear-classifier seed as a structural reference only. Keep the same artifact/state directories and the same plan-template paths, but rewrite the docs for the nanoBragg task.

**Step 2: Write the new task file with a bounded subsystem contract**

In `docs/tasks/port_nanobragg_accumulation_to_pytorch.md`, specify:
- the source file path `src_c/nanoBragg.c`
- the scoped detector pixel accumulation subsystem
- required restructuring into small PyTorch helpers
- canonical task artifact `state/task.md`
- visible check expectation `pytest -q`
- explicit out-of-scope list:
  - full `nanoBragg.c` port
  - CLI parsing
  - file I/O
  - CUDA/GPU support
  - performance targets

**Step 3: Document the PyTorch environment assumption**

In both `README.md` and `docs/index.md`, state exactly:
- the trial environment is assumed to already provide `torch`
- agents should verify availability with `python -c "import torch; print(torch.__version__)"`
- visible verification command is `pytest -q`

Do not add `requirements.txt` or `pyproject.toml` in this task.

**Step 4: Run the seed-shape test again**

Run:
```bash
pytest tests/test_demo_task_nanobragg_seed.py -q
```

Expected:
- still FAIL because the source reference, PyTorch skeleton, and smoke fixtures do not exist yet.

**Step 5: Commit the scaffold docs**

```bash
git add examples/demo_task_nanobragg_accumulation_port/AGENTS.md \
  examples/demo_task_nanobragg_accumulation_port/README.md \
  examples/demo_task_nanobragg_accumulation_port/docs \
  examples/demo_task_nanobragg_accumulation_port/artifacts \
  examples/demo_task_nanobragg_accumulation_port/state
git commit -m "feat: add nanoBragg demo seed scaffold"
```

### Task 3: Stage the visible C reference and fixture schema

**Files:**
- Create: `examples/demo_task_nanobragg_accumulation_port/src_c/nanoBragg.c`
- Create: `examples/demo_task_nanobragg_accumulation_port/src_c/README.md`
- Create: `examples/demo_task_nanobragg_accumulation_port/fixtures/visible/README.md`
- Create: `examples/demo_task_nanobragg_accumulation_port/fixtures/visible/case_small.json`
- Create: `examples/demo_task_nanobragg_accumulation_port/fixtures/visible/case_thickness.json`
- Read: `../nanoBragg/golden_suite_generator/nanoBragg.c`
- Read: `docs/plans/2026-03-05-nanobragg-subsystem-task-spec.md`

**Step 1: Copy the source file into the visible seed**

Copy `../nanoBragg/golden_suite_generator/nanoBragg.c` to:
- `examples/demo_task_nanobragg_accumulation_port/src_c/nanoBragg.c`

Do not trim or rewrite it in this task. The task file and `src_c/README.md` should point the agent to the relevant line ranges instead.

**Step 2: Add a narrow source README**

In `src_c/README.md`, identify:
- the outer detector pixel loops
- the accumulation factors in scope
- the explicit out-of-scope regions to ignore
- the warning that the task is a bounded subsystem port, not a transliteration exercise

**Step 3: Add two visible fixture files and document their schema**

Use JSON fixtures with only primitive types. Each visible case should define:
- detector dimensions
- oversample settings
- per-pixel coordinate inputs
- source vectors / wavelengths
- phi values
- mosaic-domain inputs
- any precomputed scalar factors included in scope
- expected tensor shape
- optional trace-tap metadata

Do not embed hidden expected output tensors in visible fixtures.

**Step 4: Run the seed-shape test again**

Run:
```bash
pytest tests/test_demo_task_nanobragg_seed.py -q
```

Expected:
- still FAIL because the PyTorch skeleton and visible smoke tests do not exist yet.

**Step 5: Commit the source staging and fixture schema**

```bash
git add examples/demo_task_nanobragg_accumulation_port/src_c \
  examples/demo_task_nanobragg_accumulation_port/fixtures/visible
git commit -m "feat: stage visible nanoBragg source and fixture schema"
```

### Task 4: Add the PyTorch skeleton and visible smoke checks

**Files:**
- Create: `examples/demo_task_nanobragg_accumulation_port/torch_port/__init__.py`
- Create: `examples/demo_task_nanobragg_accumulation_port/torch_port/accumulation.py`
- Create: `examples/demo_task_nanobragg_accumulation_port/torch_port/geometry.py`
- Create: `examples/demo_task_nanobragg_accumulation_port/torch_port/types.py`
- Create: `examples/demo_task_nanobragg_accumulation_port/tests/test_smoke_accumulation.py`
- Modify: `tests/test_demo_task_nanobragg_seed.py`
- Read: `examples/demo_task_linear_classifier_port/rust/tests/smoke_linear_classifier.rs`

**Step 1: Extend the repo-level seed test to assert the smoke entrypoint details**

Add assertions that `tests/test_smoke_accumulation.py` contains:
- `import torch`
- `from torch_port.accumulation import`
- at least one `assert_close` or equivalent tensor comparison
- at least one shape assertion

**Step 2: Run the seed-shape test to verify the new assertions fail**

Run:
```bash
pytest tests/test_demo_task_nanobragg_seed.py -q
```

Expected:
- FAIL because the PyTorch skeleton and smoke test do not exist yet.

**Step 3: Add minimal skeleton modules and a smoke test**

Create placeholder modules with docstrings and explicit `NotImplementedError` or stubbed function signatures for:
- loading a visible fixture
- preparing geometry tensors
- computing accumulation outputs

Create `tests/test_smoke_accumulation.py` with two smoke tests:
- one that loads `fixtures/visible/case_small.json` and asserts the returned tensor shape is correct
- one that checks finite outputs for `case_thickness.json`

Keep the smoke checks intentionally incomplete. Do not include full parity data.

**Step 4: Run the repo-level seed test and the seed-local smoke test**

Run:
```bash
pytest tests/test_demo_task_nanobragg_seed.py -q
pytest examples/demo_task_nanobragg_accumulation_port/tests/test_smoke_accumulation.py -q
```

Expected:
- `tests/test_demo_task_nanobragg_seed.py`: PASS
- `examples/demo_task_nanobragg_accumulation_port/tests/test_smoke_accumulation.py`: FAIL because the skeleton still raises `NotImplementedError`

**Step 5: Commit the visible test harness skeleton**

```bash
git add tests/test_demo_task_nanobragg_seed.py \
  examples/demo_task_nanobragg_accumulation_port/torch_port \
  examples/demo_task_nanobragg_accumulation_port/tests
git commit -m "test: add nanoBragg visible smoke harness skeleton"
```

### Task 5: Make the visible seed self-consistent and verify provisioning compatibility

**Files:**
- Modify: `examples/demo_task_nanobragg_accumulation_port/docs/index.md`
- Modify: `examples/demo_task_nanobragg_accumulation_port/README.md`
- Modify: `examples/demo_task_nanobragg_accumulation_port/tests/test_smoke_accumulation.py`
- Modify: `examples/demo_task_nanobragg_accumulation_port/torch_port/accumulation.py`
- Create: `tests/test_demo_nanobragg_provisioning.py`
- Read: `orchestrator/demo/provisioning.py`
- Read: `tests/test_demo_provisioning.py`

**Step 1: Write a failing provisioning test for the new seed**

Create `tests/test_demo_nanobragg_provisioning.py` that:
- provisions a temporary trial from `examples/demo_task_nanobragg_accumulation_port`
- asserts `state/task.md` exists in both `direct-run/` and `workflow-run/`
- asserts staged workflow assets exist in `workflow-run/workflows/examples/` and `workflow-run/prompts/workflows/`
- asserts the visible nanoBragg files survive provisioning unchanged

**Step 2: Run the new provisioning test to verify it fails**

Run:
```bash
pytest tests/test_demo_nanobragg_provisioning.py -q
```

Expected:
- FAIL because the seed-local smoke test and task file path wiring are not yet fully self-consistent.

**Step 3: Fix only the seed-local inconsistencies needed for provisioning**

Make the smallest changes needed so the seed can be copied into worktrees and still expose:
- `state/task.md`
- `pytest -q` as the visible check command
- stable relative fixture paths from `tests/test_smoke_accumulation.py`

Do not implement the hidden evaluator in this task.

**Step 4: Run the focused verification suite**

Run:
```bash
pytest tests/test_demo_task_nanobragg_seed.py tests/test_demo_nanobragg_provisioning.py -q
```

Expected:
- PASS.

**Step 5: Commit the provisionable visible seed**

```bash
git add tests/test_demo_nanobragg_provisioning.py \
  examples/demo_task_nanobragg_accumulation_port
git commit -m "feat: add provisionable nanoBragg demo seed"
```
