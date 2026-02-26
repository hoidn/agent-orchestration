# Prompt Consume Scope and Scalar Artifacts Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the ADR in `docs/plans/2026-02-26-adr-prompt-consume-scope-and-scalar-artifacts.md` by separating runtime consumes from prompt-visible consumes and adding native scalar artifact publish/consume support.

**Architecture:** Add `prompt_consumes` as a provider-step subset of `consumes` used only for prompt injection. Extend top-level artifact contracts with `kind: relpath|scalar`; keep relpath pointer behavior intact while allowing scalar values to be published/consumed without pointer-file indirection.

**Tech Stack:** Python 3.11 (`orchestrator/loader.py`, `orchestrator/workflow/executor.py`, `orchestrator/contracts/prompt_contract.py`), pytest, spec docs, example workflows.

---

### Task 1: Loader Red Tests for `prompt_consumes`

**Files:**
- Modify: `tests/test_loader_validation.py`

**Step 1: Add failing tests**

Add:
- `test_v12_prompt_consumes_requires_list_of_strings`
- `test_v12_prompt_consumes_requires_consumes`
- `test_v12_prompt_consumes_must_be_subset_of_consumes`

Expected validation messages:
- `prompt_consumes must be a list of artifact names`
- `prompt_consumes requires consumes`
- `prompt_consumes artifact '<name>' must appear in consumes`

**Step 2: Run red tests**

Run:
```bash
pytest tests/test_loader_validation.py -k "prompt_consumes" -v
```

Expected: FAIL.

**Step 3: Commit tests-only**

```bash
git add tests/test_loader_validation.py
git commit -m "test: add loader red tests for prompt_consumes"
```

---

### Task 2: Implement Loader Validation for `prompt_consumes`

**Files:**
- Modify: `orchestrator/loader.py`
- Test: `tests/test_loader_validation.py`

**Step 1: Add validation logic**

Rules:
- `prompt_consumes` valid only for v1.2+
- must be a list of non-empty strings
- step must define `consumes`
- each `prompt_consumes` entry must match a `consumes[*].artifact`

**Step 2: Run focused tests**

Run:
```bash
pytest tests/test_loader_validation.py -k "prompt_consumes or v12_" -v
```

Expected: PASS.

**Step 3: Commit**

```bash
git add orchestrator/loader.py tests/test_loader_validation.py
git commit -m "feat: validate prompt_consumes as subset of consumes"
```

---

### Task 3: Prompt Injection Red Tests for Subset Behavior

**Files:**
- Modify: `tests/test_prompt_contract_injection.py`

**Step 1: Add failing tests**

Add:
- `test_prompt_consumes_injects_only_selected_artifacts`
- `test_missing_prompt_consumes_injects_all_consumed_artifacts` (back-compat)
- `test_prompt_consumes_empty_list_injects_no_consumed_artifacts_block`

**Step 2: Run red tests**

Run:
```bash
pytest tests/test_prompt_contract_injection.py -k "prompt_consumes" -v
```

Expected: FAIL.

**Step 3: Commit tests-only**

```bash
git add tests/test_prompt_contract_injection.py
git commit -m "test: add red tests for prompt_consumes injection scope"
```

---

### Task 4: Implement `prompt_consumes` Injection Filtering

**Files:**
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/contracts/prompt_contract.py` (only if helper typing needs widening)
- Test: `tests/test_prompt_contract_injection.py`

**Step 1: Filter consumed map before rendering**

In `_apply_consumes_prompt_injection`:
- if `prompt_consumes` omitted: keep current behavior (inject all resolved consumes)
- if provided: include only those keys
- if resulting set empty: inject nothing

**Step 2: Ensure deterministic output order remains sorted**

Keep existing sorted artifact rendering contract.

**Step 3: Run tests**

Run:
```bash
pytest tests/test_prompt_contract_injection.py -v
```

Expected: PASS.

**Step 4: Commit**

```bash
git add orchestrator/workflow/executor.py orchestrator/contracts/prompt_contract.py tests/test_prompt_contract_injection.py
git commit -m "feat: support prompt_consumes subset for consumed-artifact injection"
```

---

### Task 5: Loader Red Tests for Scalar Artifact Contracts

**Files:**
- Modify: `tests/test_loader_validation.py`

**Step 1: Add failing tests**

Add:
- `test_v12_artifact_kind_scalar_accepts_non_relpath_types`
- `test_v12_artifact_kind_scalar_rejects_relpath_pointer_fields`
- `test_v12_artifact_kind_relpath_requires_pointer`
- `test_v12_artifact_kind_defaults_to_relpath_for_back_compat`

**Step 2: Run red tests**

Run:
```bash
pytest tests/test_loader_validation.py -k "artifact_kind or scalar" -v
```

Expected: FAIL.

**Step 3: Commit tests-only**

```bash
git add tests/test_loader_validation.py
git commit -m "test: add loader red tests for scalar artifact kind"
```

---

### Task 6: Implement `kind: scalar|relpath` in Loader

**Files:**
- Modify: `orchestrator/loader.py`
- Test: `tests/test_loader_validation.py`

**Step 1: Extend artifact registry schema validation**

Rules:
- `kind` allowed values: `relpath`, `scalar`
- default `kind` = `relpath` (back-compat)
- `kind: relpath`:
  - requires `type: relpath`
  - requires `pointer`
- `kind: scalar`:
  - `type` must be one of `enum|integer|float|bool`
  - reject `pointer`, `under`, `must_exist_target`

**Step 2: Run tests**

Run:
```bash
pytest tests/test_loader_validation.py -k "artifact_kind or scalar or v12_" -v
```

Expected: PASS.

**Step 3: Commit**

```bash
git add orchestrator/loader.py tests/test_loader_validation.py
git commit -m "feat: add scalar artifact kind validation"
```

---

### Task 7: Runtime Red Tests for Scalar Publish/Consume

**Files:**
- Modify: `tests/test_artifact_dataflow_integration.py`
- Modify: `tests/test_prompt_contract_injection.py` (scalar rendering case)

**Step 1: Add failing integration tests**

Add:
- `test_scalar_publish_records_typed_value`
- `test_scalar_consume_enforces_freshness`
- `test_provider_prompt_injection_renders_scalar_consumed_value`

Minimal workflow shape:
- scalar artifact `failed_count` (`kind: scalar`, `type: integer`)
- producer publishes from expected output integer file
- consumer consumes with policy/freshness

**Step 2: Run red tests**

Run:
```bash
pytest tests/test_artifact_dataflow_integration.py -k "scalar" -v
pytest tests/test_prompt_contract_injection.py -k "scalar" -v
```

Expected: FAIL.

**Step 3: Commit tests-only**

```bash
git add tests/test_artifact_dataflow_integration.py tests/test_prompt_contract_injection.py
git commit -m "test: add red runtime tests for scalar artifact publish/consume"
```

---

### Task 8: Implement Scalar Runtime Behavior

**Files:**
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/contracts/prompt_contract.py`
- Test: `tests/test_artifact_dataflow_integration.py`, `tests/test_prompt_contract_injection.py`

**Step 1: Update consume resolution branch by artifact kind**

In `_enforce_consumes_contract`:
- read artifact spec kind
- `relpath`: keep existing pointer materialization behavior
- `scalar`: skip pointer write, but still update consume ledgers and resolved consume map

**Step 2: Update value typing checks**

- `relpath` consume value must be string path
- `scalar` consume value can be int/float/bool/str (enum string)

**Step 3: Prompt rendering support for scalar values**

- widen renderer to accept `Dict[str, Any]`
- serialize scalar values deterministically (`str(value)` is acceptable for first cut)

**Step 4: Run tests**

Run:
```bash
pytest tests/test_artifact_dataflow_integration.py -v
pytest tests/test_prompt_contract_injection.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add orchestrator/workflow/executor.py orchestrator/contracts/prompt_contract.py tests/test_artifact_dataflow_integration.py tests/test_prompt_contract_injection.py
git commit -m "feat: support scalar artifacts in v1.2 publish/consume flow"
```

---

### Task 9: Spec + Example Workflow Updates

**Files:**
- Modify: `specs/dsl.md`
- Modify: `specs/providers.md`
- Modify: `specs/acceptance/index.md`
- Modify: `specs/versioning.md`
- Modify: `workflows/examples/backlog_plan_execute_v1_2_dataflow.yaml`
- Modify: `tests/test_workflow_examples_v0.py`

**Step 1: Document new DSL fields and artifact kind**

- `prompt_consumes` contract
- artifact `kind` semantics
- back-compat default behavior

**Step 2: Update example to show prompt noise minimization**

In v1.2 example review step:
- include multiple consumes
- include `prompt_consumes` subset with only reasoning-critical artifacts

**Step 3: Update acceptance catalog**

Add criteria for:
- prompt subset injection
- scalar artifact validation and runtime consume behavior

**Step 4: Run tests**

Run:
```bash
pytest tests/test_workflow_examples_v0.py -v
pytest tests/test_loader_validation.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add specs/dsl.md specs/providers.md specs/acceptance/index.md specs/versioning.md workflows/examples/backlog_plan_execute_v1_2_dataflow.yaml tests/test_workflow_examples_v0.py
git commit -m "docs: specify prompt_consumes and scalar artifacts for v1.2"
```

---

## Final Verification

Run:
```bash
pytest tests/test_loader_validation.py -v
pytest tests/test_prompt_contract_injection.py -v
pytest tests/test_artifact_dataflow_integration.py -v
pytest tests/test_workflow_examples_v0.py -v
pytest tests/test_workflow_output_contract_integration.py -v
```

Expected:
- No regressions in existing output-contract and v1.2 dataflow behavior.
- New subset/scalar behaviors fully covered.

## Rollout Notes

- This plan is intentionally backward-compatible for existing v1.2 workflows.
- `prompt_consumes` is opt-in and defaults to current "inject all consumes" behavior.
- Scalar artifacts remove pointer-file noise but do not change relpath semantics.
