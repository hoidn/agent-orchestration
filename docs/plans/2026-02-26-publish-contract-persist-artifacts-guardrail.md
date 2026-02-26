# Publish Contract vs Artifact Persistence Guardrail Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent `missing_result_artifacts` publish failures by rejecting workflows that declare `publishes` while disabling artifact persistence (`persist_artifacts_in_state: false`) on the same step.

**Architecture:** Add a loader-time validation rule so invalid workflows fail fast with a clear contract message. Keep executor runtime behavior unchanged. Add a regression test for the failure mode and document the rule in DSL/acceptance specs.

**Tech Stack:** Python 3.11, `orchestrator/loader.py`, pytest loader tests, spec docs.

---

### Task 1: Add Red Loader Test for the Contradiction

**Files:**
- Modify: `tests/test_loader_validation.py`

**Step 1: Write failing test**

Add:
- `test_v12_publishes_incompatible_with_persist_artifacts_disabled`

Test workflow should include:
- `version: "1.2"`
- top-level `artifacts` with `execution_log`
- step with:
  - `expected_outputs` producing `execution_log_path`
  - `publishes: [{artifact: execution_log, from: execution_log_path}]`
  - `persist_artifacts_in_state: false`

Assertion target:
```python
assert any(
    "publishes requires persist_artifacts_in_state to be true" in str(err.message)
    for err in exc_info.value.errors
)
```

**Step 2: Run test to verify RED**

Run:
```bash
pytest tests/test_loader_validation.py -k "publishes_incompatible_with_persist_artifacts_disabled" -v
```

Expected: FAIL (no loader rule yet).

**Step 3: Commit tests-only**

```bash
git add tests/test_loader_validation.py
git commit -m "test: add loader red test for publishes/persist_artifacts contradiction"
```

---

### Task 2: Implement Loader Validation Rule

**Files:**
- Modify: `orchestrator/loader.py`
- Test: `tests/test_loader_validation.py`

**Step 1: Add validation in step pass**

Inside `_validate_steps`, when processing a step:
```python
if 'publishes' in step and step.get('persist_artifacts_in_state') is False:
    self._add_error(
        f"Step '{name}': publishes requires persist_artifacts_in_state to be true"
    )
```

Placement: before/alongside existing `publishes` validation.

**Step 2: Run focused tests**

Run:
```bash
pytest tests/test_loader_validation.py -k "publishes and persist_artifacts" -v
```

Expected: PASS for new test and existing related tests.

**Step 3: Commit**

```bash
git add orchestrator/loader.py tests/test_loader_validation.py
git commit -m "feat: fail fast when publishes is used with persist_artifacts_in_state false"
```

---

### Task 3: Document the Constraint

**Files:**
- Modify: `specs/dsl.md`
- Modify: `specs/acceptance/index.md`

**Step 1: DSL docs update**

In `specs/dsl.md`, under `persist_artifacts_in_state` and `publishes` sections, add:
- `publishes` requires artifact values to be persisted in `steps.<Step>.artifacts`.
- Therefore `persist_artifacts_in_state:false` is invalid on any step that declares `publishes`.

**Step 2: Acceptance catalog update**

Add one acceptance item in `specs/acceptance/index.md`:
- Loader rejects steps combining `publishes` with `persist_artifacts_in_state:false`.

**Step 3: Run docs-impact regression tests**

Run:
```bash
pytest tests/test_loader_validation.py -k "v12_ or publishes" -v
```

Expected: PASS.

**Step 4: Commit**

```bash
git add specs/dsl.md specs/acceptance/index.md
git commit -m "docs: specify publishes requires artifact persistence"
```

---

### Task 4: Validate Against Real Workflow Repro

**Files:**
- External verification target: `/home/ollie/Documents/tmp/PtychoPINN/workflows/agent_orchestration/backlog_plan_slice_impl_review_loop.yaml`

**Step 1: Verify known-bad shape now fails at load-time**

Temporarily set in workflow:
- `SelectBacklogItem` has `publishes` plus `persist_artifacts_in_state:false`.

Run:
```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator.cli.main run \
  /home/ollie/Documents/tmp/PtychoPINN/workflows/agent_orchestration/backlog_plan_slice_impl_review_loop.yaml \
  --dry-run
```

Expected: loader validation error with clear message.

**Step 2: Restore valid workflow shape**

Remove contradiction and re-run dry-run.

Expected: validation success.

**Step 3: No commit in this repo for external workflow check**

(Only commit orchestrator changes here.)

---

## Final Verification

Run:
```bash
pytest tests/test_loader_validation.py -v
pytest tests/test_artifact_dataflow_integration.py -v
pytest tests/test_prompt_contract_injection.py -v
```

Expected:
- Loader fails fast on publish/persist contradiction.
- Existing dataflow/prompt behavior remains unchanged.

## Rollout Notes

- This is a guardrail, not a behavior change.
- Existing valid workflows are unaffected.
- Invalid workflows now fail at load-time instead of failing mid-run with `missing_result_artifacts`.
