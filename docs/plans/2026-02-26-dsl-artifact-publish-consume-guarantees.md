# DSL Artifact Publish/Consume Guarantees Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a minimal DSL-level dataflow contract so a consumer step (for example review) is guaranteed to consume the latest required producer artifact (for example from ExecutePlan/FixIssues), preventing stale-pointer bugs.

**Architecture:** Introduce a small v1.2 DSL extension with a top-level `artifacts` registry plus step-level `publishes` and `consumes`. Keep `expected_outputs` as the single file-validation mechanism, and map `publishes.from` to an existing `expected_outputs.name` so there is no second artifact-writing path. Enforce producer/consumer freshness in `WorkflowExecutor` using a small runtime ledger persisted in `state.json`, with fail-fast contract violations (`exit_code=2`) before provider/command execution.

**Tech Stack:** Python 3.11+, YAML loader/validator (`orchestrator/loader.py`), runtime executor (`orchestrator/workflow/executor.py`), persisted run state (`orchestrator/state.py`), pytest.

---

## DSL Contract (MVP)

```yaml
version: "1.2"
artifacts:
  execution_log:
    pointer: state/execution_log_path.txt
    type: relpath
    under: artifacts/work
    must_exist_target: true

steps:
  - name: ExecutePlan
    expected_outputs:
      - name: execution_log_path
        path: state/execution_log_path.txt
        type: relpath
        under: artifacts/work
        must_exist_target: true
    publishes:
      - artifact: execution_log
        from: execution_log_path

  - name: FixIssues
    expected_outputs:
      - name: execution_log_path
        path: state/execution_log_path.txt
        type: relpath
        under: artifacts/work
        must_exist_target: true
    publishes:
      - artifact: execution_log
        from: execution_log_path

  - name: ReviewImplVsPlan
    consumes:
      - artifact: execution_log
        producers: [ExecutePlan, FixIssues]
        policy: latest_successful
        freshness: since_last_consume
```

MVP rules:
- Version gate: `artifacts`, `publishes`, and `consumes` require `version: "1.2"`.
- `publishes.from` must reference a local `expected_outputs.name`.
- Published artifact contract must match registry contract (same type; same pointer path; compatible constraints).
- `consumes.policy` supports only `latest_successful` in MVP.
- `consumes.freshness` supports `any` (default) and `since_last_consume`.

Non-goals for this change:
- No global DAG solver.
- No cross-run artifact lineage.
- No automatic prompt rewriting beyond pointer materialization.

---

### Task 1: Add Loader Tests for v1.2 DSL Surface

**Files:**
- Modify: `tests/test_loader_validation.py`

**Step 1: Write failing tests for version gating and schema acceptance**

Add tests:
- `test_v12_artifacts_rejected_in_v1_1_1`
- `test_v12_artifacts_schema_accepts_in_v1_2`
- `test_v12_publishes_rejected_in_v1_1_1`
- `test_v12_consumes_rejected_in_v1_1_1`

Example test payload:
```python
workflow = {
    "version": "1.1.1",
    "artifacts": {
        "execution_log": {
            "pointer": "state/execution_log_path.txt",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
        }
    },
    "steps": [{"name": "X", "command": ["echo", "ok"]}],
}
```

**Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_loader_validation.py -k "v12_artifacts or v12_publishes or v12_consumes" -v
```
Expected: FAIL (feature not implemented).

**Step 3: Commit test-only change**

```bash
git add tests/test_loader_validation.py
git commit -m "test: add failing loader tests for v1.2 artifact dataflow fields"
```

---

### Task 2: Implement Loader Validation for `artifacts` / `publishes` / `consumes`

**Files:**
- Modify: `orchestrator/loader.py`
- Test: `tests/test_loader_validation.py`

**Step 1: Implement minimal loader support for v1.2**

Code changes:
- `SUPPORTED_VERSIONS` includes `"1.2"`.
- Top-level known fields include `artifacts`.
- Add `_validate_artifacts_registry(artifacts, version)`.
- Add `_validate_publishes(step, step_name, version)`.
- Add `_validate_consumes(step, step_name, version)`.
- Add cross-reference pass after step validation:
  - `publishes.from` exists in step `expected_outputs`.
  - published artifact name exists in top-level registry.
  - pointer/type contract consistency is enforced.

Add helper skeleton:
```python
def _get_expected_output_map(self, step: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for spec in step.get("expected_outputs", []):
        if isinstance(spec, dict) and isinstance(spec.get("name"), str):
            out[spec["name"]] = spec
    return out
```

**Step 2: Add more failing tests for cross-reference safety**

Add tests:
- `test_v12_publishes_from_must_reference_expected_output_name`
- `test_v12_publishes_pointer_must_match_registry_pointer`
- `test_v12_consumes_producers_must_publish_artifact`

**Step 3: Run tests**

Run:
```bash
pytest tests/test_loader_validation.py -k "v12_" -v
```
Expected: PASS.

**Step 4: Commit**

```bash
git add orchestrator/loader.py tests/test_loader_validation.py
git commit -m "feat: add v1.2 loader validation for artifacts/publishes/consumes"
```

---

### Task 3: Add Runtime Tests for Publish Ledger and Consume Enforcement

**Files:**
- Create: `tests/test_artifact_dataflow_integration.py`

**Step 1: Write failing integration tests for runtime guarantees**

Add tests:
- `test_publish_records_artifact_version_on_success`
- `test_consume_latest_successful_prefers_fixissues_over_executeplan`
- `test_consume_since_last_consume_fails_when_stale`
- `test_consume_missing_producer_output_fails_with_contract_violation`

Use tiny command-only workflows for determinism.

Example stale-consume workflow shape:
```python
{
  "version": "1.2",
  "artifacts": {
    "execution_log": {
      "pointer": "state/execution_log_path.txt",
      "type": "relpath",
      "under": "artifacts/work",
      "must_exist_target": True,
    }
  },
  "steps": [
    # producer step writes state/execution_log_path.txt + target file
    # consumer step requires freshness=since_last_consume twice; second should fail
  ]
}
```

**Step 2: Run tests to verify failure**

Run:
```bash
pytest tests/test_artifact_dataflow_integration.py -v
```
Expected: FAIL (runtime support missing).

**Step 3: Commit tests**

```bash
git add tests/test_artifact_dataflow_integration.py
git commit -m "test: add failing runtime tests for artifact publish/consume guarantees"
```

---

### Task 4: Implement Runtime Publish Ledger in State + Executor

**Files:**
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/workflow/executor.py`
- Test: `tests/test_artifact_dataflow_integration.py`

**Step 1: Add runtime ledger fields to state model (backward-compatible)**

In `RunState`, add optional dict fields:
```python
artifact_versions: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
artifact_consumes: Dict[str, Dict[str, int]] = field(default_factory=dict)
```

Keep `schema_version` unchanged for MVP compatibility (`"1.1.1"`) and treat new fields as optional in `from_dict`.

**Step 2: Record publications after successful step contract validation**

In executor, after `_apply_expected_outputs_contract` success:
- resolve each `publishes` entry from `result["artifacts"][from_name]`
- append new version record to `state.artifact_versions[artifact_name]`:
```python
{
  "version": next_int,
  "value": artifact_value,
  "producer": step_name,
  "step_index": self.current_step,
}
```
- persist via `StateManager` write path.

**Step 3: Run publish tests**

Run:
```bash
pytest tests/test_artifact_dataflow_integration.py -k "publish_records" -v
```
Expected: PASS for publish test(s).

**Step 4: Commit**

```bash
git add orchestrator/state.py orchestrator/workflow/executor.py tests/test_artifact_dataflow_integration.py
git commit -m "feat: persist artifact publication ledger in run state"
```

---

### Task 5: Implement Consume Preflight Enforcement (`latest_successful` + freshness)

**Files:**
- Modify: `orchestrator/workflow/executor.py`
- Test: `tests/test_artifact_dataflow_integration.py`

**Step 1: Implement preflight consume resolver**

Add executor helper:
```python
def _enforce_consumes_contract(self, step: Dict[str, Any], step_name: str, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # return None when contract satisfied
    # return failed result dict (exit_code=2, contract_violation) on failure
```

Behavior:
- For each `consumes` entry:
  - filter versions by `producers` when provided
  - select latest version by `version` (`policy=latest_successful`)
  - enforce freshness:
    - `any`: allow
    - `since_last_consume`: selected version must be `>` last consumed version for this step+artifact
- On success:
  - rewrite canonical pointer file (`artifacts.<name>.pointer`) with selected value (single source of truth on disk)
  - update `artifact_consumes[step_name][artifact_name] = selected_version`
- On failure:
  - synthesize step result with `exit_code=2`, `status=failed`, `error.type="contract_violation"`
  - do not execute command/provider.

**Step 2: Wire preflight into execution flow**

Before command/provider/wait_for dispatch in main step loop:
- call `_enforce_consumes_contract(...)`
- if non-`None` error result, persist step failure and continue through standard control-flow handling.

**Step 3: Run consume tests**

Run:
```bash
pytest tests/test_artifact_dataflow_integration.py -k "consume" -v
```
Expected: PASS.

**Step 4: Commit**

```bash
git add orchestrator/workflow/executor.py tests/test_artifact_dataflow_integration.py
git commit -m "feat: enforce consume contracts with latest-successful freshness checks"
```

---

### Task 6: Spec and Acceptance Documentation

**Files:**
- Modify: `specs/dsl.md`
- Modify: `specs/state.md`
- Modify: `specs/versioning.md`
- Modify: `specs/variables.md`
- Modify: `specs/acceptance/index.md`

**Step 1: Document v1.2 DSL additions**

In `specs/dsl.md`:
- add top-level `artifacts` schema
- add step fields `publishes` and `consumes`
- define `policy: latest_successful` and `freshness: any|since_last_consume`
- define failure mode as contract violation (`exit 2`)

In `specs/state.md`:
- add optional runtime fields `artifact_versions` and `artifact_consumes`
- describe persistence semantics.

In `specs/versioning.md`:
- add v1.2 section for dataflow contracts.

In `specs/variables.md`:
- note that consumed artifact resolution materializes canonical pointer files before step execution.

In `specs/acceptance/index.md` add AT items:
- loader gates `artifacts/publishes/consumes` behind v1.2
- publish ledger records versions deterministically
- consume latest-successful selection
- consume freshness enforcement (`since_last_consume`)
- stale/missing consume contract failure shape

**Step 2: Run spec-focused checks**

Run:
```bash
pytest tests/test_loader_validation.py -k "v12_" -v
pytest tests/test_artifact_dataflow_integration.py -v
```
Expected: PASS.

**Step 3: Commit**

```bash
git add specs/dsl.md specs/state.md specs/versioning.md specs/variables.md specs/acceptance/index.md
git commit -m "docs: specify v1.2 artifact publish/consume DSL and acceptance criteria"
```

---

### Task 7: End-to-End Regression and Example Workflow Coverage

**Files:**
- Modify: `workflows/examples/backlog_plan_execute_v0.yaml` (or create a v1.2 example)
- Modify: `tests/test_workflow_examples_v0.py`
- Modify: `tests/test_workflow_output_contract_integration.py` (if needed for shared helper coverage)

**Step 1: Add a focused v1.2 example**

Preferred: create `workflows/examples/backlog_plan_execute_v1_2_dataflow.yaml` with:
- `artifacts.execution_log`
- `ExecutePlan` and `FixIssues` publishing same artifact
- `ReviewPlan` consuming latest.

**Step 2: Add example runtime test**

In `tests/test_workflow_examples_v0.py` (or a new file), assert:
- second review after fix consumes newer publication
- stale consume path fails when freshness cannot be met.

**Step 3: Run targeted + broad regression**

Run:
```bash
pytest tests/test_loader_validation.py -k "v12_" -v
pytest tests/test_artifact_dataflow_integration.py -v
pytest tests/test_workflow_examples_v0.py -k "dataflow or backlog" -v
pytest tests/test_workflow_output_contract_integration.py -v
```
Expected: PASS.

**Step 4: Final commit**

```bash
git add workflows/examples tests/test_workflow_examples_v0.py tests/test_workflow_output_contract_integration.py
git commit -m "test: add v1.2 workflow example and regression coverage for dataflow guarantees"
```

---

## Final Verification Checklist

Run before merge:

```bash
pytest tests/test_loader_validation.py -k "v12_" -v
pytest tests/test_artifact_dataflow_integration.py -v
pytest tests/test_workflow_examples_v0.py -k "dataflow" -v
pytest tests/test_workflow_output_contract_integration.py -v
pytest tests/test_state_manager.py -v
```

Expected outcomes:
- All new v1.2 tests pass.
- Existing 1.1/1.1.1 workflows still pass unchanged.
- Contract-violation failures are deterministic and include `error.type == "contract_violation"`.

## Rollout Notes

- Keep feature gated to `version: "1.2"` to avoid breaking old workflows.
- Migrate target workflows by first adding top-level `artifacts`, then `publishes`, then `consumes`.
- For the specific backlog loop bug class: both `ExecutePlan` and `FixIssues` must publish `execution_log`, and review must consume `execution_log` with `policy: latest_successful`.
