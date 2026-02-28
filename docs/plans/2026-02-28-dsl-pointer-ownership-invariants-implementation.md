# DSL Pointer Ownership Invariants Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move pointer-ownership conventions from prompt discipline into deterministic DSL/executor semantics so provider steps can safely consume prewritten output pointers without mutating them.

**Architecture:** Add one additive `expected_outputs` field: `path_mode: write|prewritten` (default `write`). `write` preserves current behavior. `prewritten` encodes deterministic handoff ownership: pointer file must exist before step execution, must remain unchanged across the step, and the referenced target is validated via existing relpath checks (`under`, `must_exist_target`). This keeps workflow YAML readable while making the universal handoff invariant enforceable at runtime.

**Tech Stack:** Python (`orchestrator/loader.py`, `orchestrator/workflow/executor.py`, `orchestrator/contracts/prompt_contract.py`), DSL spec/docs (`specs/dsl.md`, `docs/workflow_drafting_guide.md`), pytest.

---

## Design Decisions (Normative)

1. Add `expected_outputs[*].path_mode` (optional):
   - `write` (default): current behavior; step writes/updates the value file at `path`.
   - `prewritten` (relpath only): value file at `path` is prepared before step and is read-only during step execution.

2. `prewritten` runtime invariants:
   - preflight: `path` file exists before step starts (otherwise contract violation).
   - immutability: bytes at `path` are unchanged after successful execution.
   - parsing/validation: parsed using existing type parser and relpath guards (`under`, canonicalization, `must_exist_target`).

3. Prompt injection behavior:
   - `render_output_contract_block` includes `path_mode`.
   - For `path_mode: prewritten`, output contract text explicitly instructs: read the path from the file and do not modify the file itself.

4. Compatibility:
   - additive change; existing workflows continue unchanged.
   - no DSL version bump required.

5. Non-goals:
   - no semantic "plan complete" validator.
   - no new artifact policy types.

---

### Task 1: Loader + Schema Support for `path_mode`

**Files:**
- Modify: `orchestrator/loader.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `specs/dsl.md`

**Step 1: Add failing loader tests**

Add tests in `tests/test_loader_validation.py`:
- accepts `path_mode: write` and `path_mode: prewritten` for `type: relpath`.
- rejects non-string `path_mode`.
- rejects unknown `path_mode` values.
- rejects `path_mode: prewritten` when `type != relpath`.

Example failing test payload:

```python
workflow = {
    "version": "1.1.1",
    "name": "prewritten-pointer",
    "steps": [{
        "name": "Review",
        "provider": "codex",
        "expected_outputs": [{
            "name": "code_review_path",
            "path": "state/code_review_path.txt",
            "type": "relpath",
            "under": "artifacts/review",
            "path_mode": "prewritten",
        }],
    }],
}
```

**Step 2: Run red tests**

Run:
```bash
pytest tests/test_loader_validation.py -k "path_mode or prewritten" -v
```
Expected: FAIL.

**Step 3: Implement loader validation**

In `_validate_expected_outputs(...)`:
- add optional `path_mode` parsing.
- allowed values: `write`, `prewritten`.
- enforce: `path_mode: prewritten` requires `type: relpath`.

Minimal shape:

```python
path_mode = spec.get("path_mode", "write")
if not isinstance(path_mode, str): ...
elif path_mode not in {"write", "prewritten"}: ...
if path_mode == "prewritten" and spec.get("type") != "relpath": ...
```

**Step 4: Re-run tests**

Run:
```bash
pytest tests/test_loader_validation.py -k "path_mode or prewritten" -v
pytest tests/test_loader_validation.py -v
```
Expected: PASS.

**Step 5: Update spec text**

In `specs/dsl.md`, document `path_mode` under `expected_outputs` including behavior and defaults.

**Step 6: Commit**

```bash
git add orchestrator/loader.py tests/test_loader_validation.py specs/dsl.md
git commit -m "feat(dsl): add expected_outputs.path_mode for pointer ownership"
```

---

### Task 2: Prompt Contract Injection for `prewritten`

**Files:**
- Modify: `orchestrator/contracts/prompt_contract.py`
- Modify: `tests/test_prompt_contract_injection.py`

**Step 1: Add failing prompt-injection test**

Add test asserting output contract block includes:
- `path_mode: prewritten`
- guidance line indicating pointer file is read-only for this step.

**Step 2: Run red test**

Run:
```bash
pytest tests/test_prompt_contract_injection.py -k "path_mode or prewritten" -v
```
Expected: FAIL.

**Step 3: Implement renderer update**

In `render_output_contract_block(...)`:
- emit `path_mode` when present.
- when `path_mode == "prewritten"`, append one explicit instruction line.

**Step 4: Re-run tests**

Run:
```bash
pytest tests/test_prompt_contract_injection.py -k "path_mode or prewritten or output_contract" -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add orchestrator/contracts/prompt_contract.py tests/test_prompt_contract_injection.py
git commit -m "feat(prompt): annotate prewritten output pointers in output contract block"
```

---

### Task 3: Executor Preflight + Immutable Pointer Enforcement

**Files:**
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_workflow_output_contract_integration.py`

**Step 1: Add failing integration tests**

Add tests:
- `test_prewritten_pointer_requires_preexisting_file`: missing pointer file before step causes contract failure.
- `test_prewritten_pointer_rejects_pointer_mutation`: step changes pointer file content -> contract violation.
- `test_prewritten_pointer_allows_target_write_without_pointer_change`: step writes target file only, passes contract.

Workflow shape for mutation case:
```yaml
expected_outputs:
  - name: code_review_path
    path: state/code_review_path.txt
    type: relpath
    under: artifacts/review
    must_exist_target: true
    path_mode: prewritten
```

**Step 2: Run red tests**

Run:
```bash
pytest tests/test_workflow_output_contract_integration.py -k "prewritten_pointer" -v
```
Expected: FAIL.

**Step 3: Implement preflight snapshot in executor**

Add helper to capture prewritten expected output files before step execution.
- Called for command and provider steps.
- For each `path_mode: prewritten` spec:
  - verify `path` exists pre-step.
  - snapshot exact bytes/text content.
- If missing, return `contract_violation` before step runs.

**Step 4: Enforce immutability in post-step contract phase**

In `_apply_expected_outputs_contract(...)` path:
- after successful step exit and before parsing expected outputs:
  - compare current file content at `path` vs preflight snapshot for each prewritten spec.
  - on mismatch: fail with `contract_violation` reason `prewritten_output_modified`.

Reuse existing parsing to validate the (unchanged) relpath value + target checks.

**Step 5: Re-run tests**

Run:
```bash
pytest tests/test_workflow_output_contract_integration.py -k "prewritten_pointer" -v
pytest tests/test_workflow_output_contract_integration.py -v
```
Expected: PASS.

**Step 6: Commit**

```bash
git add orchestrator/workflow/executor.py tests/test_workflow_output_contract_integration.py
git commit -m "feat(executor): enforce prewritten pointer ownership for expected outputs"
```

---

### Task 4: Output Contract Validator Coverage for `prewritten` Edge Cases

**Files:**
- Modify: `tests/test_output_contract.py`
- Optional: `orchestrator/contracts/output_contract.py` (only if gaps found)

**Step 1: Add focused tests**

Add tests that combine `path_mode: prewritten` with existing relpath semantics:
- basename normalization under `under` root still applies.
- symlink escape violations still fail.
- `must_exist_target` remains enforced.

These tests should ensure `path_mode` does not weaken existing path security.

**Step 2: Run tests**

Run:
```bash
pytest tests/test_output_contract.py -k "relpath and (prewritten or normalize or symlink or must_exist_target)" -v
```
Expected: PASS.

**Step 3: Commit**

```bash
git add tests/test_output_contract.py orchestrator/contracts/output_contract.py
git commit -m "test(output_contract): verify prewritten mode preserves relpath safety semantics"
```

---

### Task 5: Docs + Workflow Drafting Guidance

**Files:**
- Modify: `specs/dsl.md`
- Modify: `docs/workflow_drafting_guide.md`
- Modify: `workflows/examples/backlog_plan_execute_v1_2_dataflow.yaml` (or closest maintained example)

**Step 1: Update drafting guide pattern**

Add a short "Prepared Pointer" subsection:
- When a deterministic pre-step chooses path, mark downstream `expected_outputs` as `path_mode: prewritten`.
- Prompt should read pointer, write target, not pointer.

**Step 2: Update example workflow snippet**

In one maintained example, demonstrate:
- pre-step writes `state/code_review_path.txt`
- provider step uses `expected_outputs` with `path_mode: prewritten`.

**Step 3: Run example tests/docs checks**

Run:
```bash
pytest tests/test_workflow_examples_v0.py -k "backlog or artifact or contract" -v
```
Expected: PASS.

**Step 4: Commit**

```bash
git add specs/dsl.md docs/workflow_drafting_guide.md workflows/examples/backlog_plan_execute_v1_2_dataflow.yaml tests/test_workflow_examples_v0.py
git commit -m "docs(workflows): document prewritten pointer ownership pattern"
```

---

### Task 6: End-to-End Verification + Rollout Notes

**Files:**
- Modify: `docs/plans/2026-02-28-dsl-pointer-ownership-invariants-implementation.md` (status notes)
- Optional: `README.md` changelog snippet if used in repo practice

**Step 1: Run full selector set for touched areas**

Run:
```bash
pytest tests/test_loader_validation.py -k "expected_outputs or path_mode or inject_output_contract" -v
pytest tests/test_prompt_contract_injection.py -v
pytest tests/test_output_contract.py -v
pytest tests/test_workflow_output_contract_integration.py -v
pytest tests/test_artifact_dataflow_integration.py -k "consume or publish or freshness" -v
pytest tests/test_workflow_examples_v0.py -k runtime -v
```
Expected: PASS.

**Step 2: Dry-run one representative workflow**

Run:
```bash
python -m orchestrator.cli.main run workflows/examples/backlog_plan_execute_v1_2_dataflow.yaml --dry-run
```
Expected: validation succeeds.

**Step 3: Record rollout compatibility notes**

Document:
- default `path_mode: write` means no migration needed.
- migration recommendation for deterministic pointer-prep workflows.

**Step 4: Commit final verification/doc updates**

```bash
git add docs/plans/2026-02-28-dsl-pointer-ownership-invariants-implementation.md README.md
git commit -m "chore: verify prewritten pointer ownership feature and document rollout"
```
