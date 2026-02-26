# Consumes Prompt Injection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `consumes` on provider steps automatically inject a deterministic “read these consumed artifacts” block into the composed prompt, so prompt files no longer need hardcoded pointer-file instructions.

**Architecture:** Keep pointer materialization as the runtime source of truth. Reuse consume resolution from `WorkflowExecutor` preflight, then render a stable prompt block from the same resolved artifact values. Add one opt-out switch (`inject_consumes`) and one placement switch (`consumes_injection_position`) for provider steps. Do not add prompt parsing or dynamic template substitution.

**Tech Stack:** Python (`orchestrator/loader.py`, `orchestrator/workflow/executor.py`, `orchestrator/contracts/prompt_contract.py`), pytest, YAML workflows/spec docs.

---

## Contract (Implementation Target)

Provider step behavior in `version: "1.2"` workflows:
- If step has `consumes` and `inject_consumes` is not `false`, inject block:

```text
## Consumed Artifacts
- plan_path: docs/plans/2026-02-26-foo.md
- execution_log: artifacts/work/latest-execution-log.md
Read these files before acting.
```

- Ordering is deterministic by artifact name.
- Values come from consume preflight resolution (same source as pointer materialization), never from prompt text.
- Injection position defaults to `prepend`; `consumes_injection_position: append` is supported.

---

### Task 1: Loader Red Tests for New Step Fields

**Files:**
- Modify: `tests/test_loader_validation.py`

**Step 1: Add failing tests**

Add tests:
- `test_v12_inject_consumes_requires_boolean`
- `test_v12_consumes_injection_position_must_be_prepend_or_append`
- `test_v12_consumes_injection_position_requires_v1_2`

Example assertion target:
```python
assert any("'inject_consumes' must be a boolean" in str(err.message) for err in exc_info.value.errors)
```

**Step 2: Run to verify red**

Run:
```bash
pytest tests/test_loader_validation.py -k "inject_consumes or consumes_injection_position" -v
```
Expected: FAIL.

**Step 3: Commit tests-only**

```bash
git add tests/test_loader_validation.py
git commit -m "test: add loader red tests for consumes prompt injection flags"
```

---

### Task 2: Implement Loader Validation for Injection Flags

**Files:**
- Modify: `orchestrator/loader.py`
- Test: `tests/test_loader_validation.py`

**Step 1: Implement minimal validation**

Rules:
- `inject_consumes` must be boolean when present.
- `consumes_injection_position` must be `prepend` or `append`.
- Both fields are valid only for `version: "1.2"`+.

Suggested validation snippet:
```python
if 'inject_consumes' in step and not isinstance(step['inject_consumes'], bool):
    self._add_error(f"Step '{name}': 'inject_consumes' must be a boolean")
```

**Step 2: Run tests**

Run:
```bash
pytest tests/test_loader_validation.py -k "inject_consumes or consumes_injection_position or v12_" -v
```
Expected: PASS.

**Step 3: Commit**

```bash
git add orchestrator/loader.py tests/test_loader_validation.py
git commit -m "feat: validate consumes prompt injection step fields"
```

---

### Task 3: Prompt-Block Rendering Red Tests

**Files:**
- Modify: `tests/test_prompt_contract_injection.py`

**Step 1: Add failing provider prompt tests**

Add tests:
- `test_provider_consumes_appends_consumed_artifacts_block_by_default`
- `test_inject_consumes_false_disables_consumes_block`
- `test_consumes_injection_position_append_places_block_after_prompt`

Use captured prompt via mocked `prepare_invocation` (pattern already in file).

**Step 2: Run to verify red**

Run:
```bash
pytest tests/test_prompt_contract_injection.py -k "consumes" -v
```
Expected: FAIL.

**Step 3: Commit tests-only**

```bash
git add tests/test_prompt_contract_injection.py
git commit -m "test: add red tests for provider consumes prompt injection"
```

---

### Task 4: Implement Consumes Prompt Rendering Helper

**Files:**
- Modify: `orchestrator/contracts/prompt_contract.py`
- Test: `tests/test_prompt_contract_injection.py`

**Step 1: Add renderer function**

Add:
```python
def render_consumed_artifacts_block(consumed: Dict[str, str]) -> str:
    lines = ["## Consumed Artifacts"]
    for name in sorted(consumed.keys()):
        lines.append(f"- {name}: {consumed[name]}")
    lines.append("Read these files before acting.")
    return "\n".join(lines) + "\n"
```

**Step 2: Keep output deterministic**
- Sort keys lexicographically.
- Keep exact heading/line format stable for tests.

**Step 3: Run focused tests**

Run:
```bash
pytest tests/test_prompt_contract_injection.py -k "consumes" -v
```
Expected: still FAIL (executor not wired yet) or partial PASS if unit coverage added.

**Step 4: Commit**

```bash
git add orchestrator/contracts/prompt_contract.py tests/test_prompt_contract_injection.py
git commit -m "feat: add deterministic consumes prompt block renderer"
```

---

### Task 5: Wire Executor to Inject Consumes for Provider Steps

**Files:**
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_prompt_contract_injection.py`
- Modify: `tests/test_artifact_dataflow_integration.py` (if runtime provenance assertion needs extension)

**Step 1: Capture consume resolution for current step**

Extend consume preflight to retain resolved artifact values for the current step in memory:
```python
state.setdefault('_resolved_consumes', {})[step_name] = {
    artifact_name: selected_value,
}
```

Do not persist `_resolved_consumes` to `state.json`.

**Step 2: Inject consumes block in provider prompt composition**

In provider prompt compose path (where output-contract suffix is appended):
- if step has `consumes`
- if `inject_consumes` is not `False`
- get resolved map from `_resolved_consumes[step_name]`
- render block and prepend/append based on `consumes_injection_position`.

Suggested method:
```python
def _apply_consumes_prompt_injection(self, step, step_name, prompt, state):
    ...
```

**Step 3: Preserve existing behavior**
- Keep `inject_output_contract` behavior unchanged.
- Injection order:
  1) base prompt from `input_file` (+ dependency injection)
  2) consumes block (prepend/append)
  3) output-contract suffix (existing)

**Step 4: Run tests**

Run:
```bash
pytest tests/test_prompt_contract_injection.py -v
pytest tests/test_artifact_dataflow_integration.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add orchestrator/workflow/executor.py tests/test_prompt_contract_injection.py tests/test_artifact_dataflow_integration.py
git commit -m "feat: auto-inject consumed artifacts into provider prompts"
```

---

### Task 6: Example Workflow + Runtime Coverage

**Files:**
- Modify: `workflows/examples/backlog_plan_execute_v1_2_dataflow.yaml`
- Modify: `tests/test_workflow_examples_v0.py`
- Modify: `workflows/examples/README_v0_artifact_contract.md`

**Step 1: Add explicit `inject_consumes` usage in v1.2 example**

In `ReviewPlan` step, add:
```yaml
inject_consumes: true
consumes_injection_position: prepend
```

**Step 2: Add runtime assertion in example test**

Capture provider prompt and assert consumed block exists with latest consumed artifact value.

**Step 3: Run tests**

Run:
```bash
pytest tests/test_workflow_examples_v0.py -k "v1_2_dataflow" -v
```
Expected: PASS.

**Step 4: Commit**

```bash
git add workflows/examples/backlog_plan_execute_v1_2_dataflow.yaml tests/test_workflow_examples_v0.py workflows/examples/README_v0_artifact_contract.md
git commit -m "test: cover consumes prompt injection in v1.2 example workflow"
```

---

### Task 7: Spec Updates

**Files:**
- Modify: `specs/providers.md`
- Modify: `specs/dsl.md`
- Modify: `specs/acceptance/index.md`
- Modify: `specs/versioning.md`

**Step 1: Document prompt composition update**

In `specs/providers.md` add consumes injection stage:
- provider prompt includes consumed-artifacts block by default for `consumes` in v1.2.

**Step 2: Document DSL keys**

In `specs/dsl.md`:
- `inject_consumes: boolean` (provider steps only, default true)
- `consumes_injection_position: prepend|append`.

**Step 3: Add acceptance criteria entries**

In `specs/acceptance/index.md` add items:
- consumes block appears in provider prompt by default
- opt-out works
- append/prepend works
- injected values match consume resolution values.

**Step 4: Run docs-impact tests**

Run:
```bash
pytest tests/test_prompt_contract_injection.py -v
pytest tests/test_loader_validation.py -k "v12_ or inject_consumes" -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add specs/providers.md specs/dsl.md specs/acceptance/index.md specs/versioning.md
git commit -m "docs: specify consumes prompt injection semantics for provider steps"
```

---

## Final Verification

Run:
```bash
pytest tests/test_loader_validation.py -k "v12_ or inject_consumes or consumes_injection_position" -v
pytest tests/test_prompt_contract_injection.py -v
pytest tests/test_artifact_dataflow_integration.py -v
pytest tests/test_workflow_examples_v0.py -v
pytest tests/test_workflow_output_contract_integration.py -v
pytest tests/test_state_manager.py -v
```

Expected:
- New consumes-injection tests pass.
- Existing output-contract injection tests remain green.
- Dataflow provenance/freshness tests remain green.
- No regressions in existing v0/v1.2 workflow examples.

## Rollout Notes

- Keep pointer files as authoritative runtime contract.
- Treat consumes prompt injection as a provider convenience layer derived from the same resolved values.
- For migrations: remove hardcoded `state/...` read instructions from prompts after `consumes` injection is enabled.
