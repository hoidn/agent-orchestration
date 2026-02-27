# Structured Deterministic I/O Bundles Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement `version: "1.3"` JSON-bundled deterministic I/O (`output_bundle`, `consume_bundle`) while preserving v1.2 compatibility and keeping workflow control flow driven by strict review/assessment artifacts.

**Architecture:** Extend the existing deterministic artifact pipeline instead of replacing it: parsed bundle fields must still end up in `steps.<Step>.artifacts`, and publish/consume ledgers remain the source of truth. Add loader-level schema validation for new v1.3 fields, runtime extraction/materialization helpers in executor/contracts, and narrow example coverage to prove end-to-end behavior. Preserve current v1.2 `expected_outputs` and pointer-file workflows unchanged.

**Tech Stack:** Python 3.11+, `orchestrator/loader.py`, `orchestrator/contracts/output_contract.py`, `orchestrator/workflow/executor.py`, pytest, YAML example workflows, spec docs.

---

## Implementation Contract (Must Hold)

1. `output_bundle` is optional, v1.3-gated, and mutually exclusive with `expected_outputs` on the same step.
2. `output_bundle.fields[*]` produce typed artifacts exactly like `expected_outputs`, including `enum`/`relpath` constraints.
3. `consume_bundle` is optional, v1.3-gated, writes one JSON file from resolved consumes after consume preflight succeeds.
4. `publishes/consumes` runtime semantics do not change; bundles are just alternate deterministic I/O packaging.
5. Workflow policy guidance is explicit: heavy execution/fix steps stay flexible (`text`), assessment/review/gate steps are strict (`json`, parse errors fail), and control flow consumes strict artifacts.

Execution note: implementation should follow @superpowers:test-driven-development and @superpowers:verification-before-completion.

---

### Task 1: Add Loader Red Tests for v1.3 Bundle Fields

**Files:**
- Modify: `tests/test_loader_validation.py`

**Step 1: Write failing tests for new DSL fields**

Add tests:
- `test_v13_output_bundle_requires_version_1_3`
- `test_v13_output_bundle_rejects_expected_outputs_on_same_step`
- `test_v13_output_bundle_requires_non_empty_fields`
- `test_v13_output_bundle_field_requires_json_pointer_and_type`
- `test_v13_consume_bundle_requires_version_1_3`
- `test_v13_consume_bundle_requires_consumes_and_subset_include`

Use assertions like:
```python
assert any("output_bundle requires version '1.3'" in str(err.message) for err in exc_info.value.errors)
```

**Step 2: Run tests to verify they fail**

Run:
```bash
pytest tests/test_loader_validation.py -k "v13 or output_bundle or consume_bundle" -v
```
Expected: FAIL on unknown/unsupported v1.3 validation paths.

**Step 3: Commit red tests**

```bash
git add tests/test_loader_validation.py
git commit -m "test: add loader red tests for v1.3 json bundle fields"
```

---

### Task 2: Implement Loader Validation and Version Gating

**Files:**
- Modify: `orchestrator/loader.py`
- Test: `tests/test_loader_validation.py`

**Step 1: Extend version support and step validation**

Implement:
- `SUPPORTED_VERSIONS` includes `"1.3"`.
- New step keys: `output_bundle`, `consume_bundle` (both v1.3+).
- Reject `output_bundle` when `expected_outputs` is also present.

Suggested shape:
```python
if "output_bundle" in step:
    if version != "1.3":
        self._add_error(f"Step '{name}': output_bundle requires version '1.3'")
    else:
        self._validate_output_bundle(step["output_bundle"], name)
```

**Step 2: Add dedicated validators**

Implement `_validate_output_bundle(...)` and `_validate_consume_bundle(...)`:
- path safety checks on `path`
- non-empty `fields`
- unique `fields[*].name`
- `json_pointer` required per field
- `consume_bundle.include` must be subset of `consumes[*].artifact` when present

**Step 3: Run focused loader tests**

Run:
```bash
pytest tests/test_loader_validation.py -k "v13 or output_bundle or consume_bundle" -v
```
Expected: PASS.

**Step 4: Run full loader validation suite**

Run:
```bash
pytest tests/test_loader_validation.py -v
```
Expected: PASS (no v1.2 regressions).

**Step 5: Commit**

```bash
git add orchestrator/loader.py tests/test_loader_validation.py
git commit -m "feat: add v1.3 loader validation for output_bundle and consume_bundle"
```

---

### Task 3: Add Red Unit Tests for Output Bundle Contract Parsing

**Files:**
- Modify: `tests/test_output_contract.py`

**Step 1: Add failing unit tests for bundle extraction**

Add tests:
- `test_validate_output_bundle_parses_supported_types`
- `test_validate_output_bundle_missing_file_raises_violation`
- `test_validate_output_bundle_invalid_json_raises_violation`
- `test_validate_output_bundle_missing_pointer_raises_violation`
- `test_validate_output_bundle_invalid_enum_raises_violation`
- `test_validate_output_bundle_relpath_constraints_are_enforced`

Example skeleton:
```python
artifacts = validate_output_bundle(bundle_spec, workspace=tmp_path)
assert artifacts["failed_count"] == 2
```

**Step 2: Run tests to verify red**

Run:
```bash
pytest tests/test_output_contract.py -k "output_bundle" -v
```
Expected: FAIL (`validate_output_bundle` missing / behavior incomplete).

**Step 3: Commit red tests**

```bash
git add tests/test_output_contract.py
git commit -m "test: add red unit coverage for output_bundle contract validation"
```

---

### Task 4: Implement Output Bundle Validation in Contract Layer

**Files:**
- Modify: `orchestrator/contracts/output_contract.py`
- Test: `tests/test_output_contract.py`

**Step 1: Add bundle validator API**

Implement:
```python
def validate_output_bundle(output_bundle: Dict[str, Any], workspace: Path) -> Dict[str, Any]:
    ...
```

Rules:
- read JSON document at `output_bundle.path`
- resolve each field via `json_pointer`
- validate with existing typed parsers (`enum|integer|float|bool|relpath`)
- return `artifacts: Dict[str, Any]`

**Step 2: Reuse existing violation model**

Reuse `ContractViolation`/`OutputContractError` with bundle-specific violation types (for example `missing_bundle_file`, `invalid_json_pointer`, `json_pointer_not_found`, `invalid_json_document`).

**Step 3: Run focused unit tests**

Run:
```bash
pytest tests/test_output_contract.py -k "output_bundle" -v
```
Expected: PASS.

**Step 4: Run full contract tests**

Run:
```bash
pytest tests/test_output_contract.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add orchestrator/contracts/output_contract.py tests/test_output_contract.py
git commit -m "feat: support deterministic output_bundle validation"
```

---

### Task 5: Integrate `output_bundle` into Executor Artifact Pipeline

**Files:**
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_workflow_output_contract_integration.py`

**Step 1: Add integration red tests**

Add tests:
- `test_command_step_persists_artifacts_from_output_bundle`
- `test_command_step_output_bundle_contract_violation_sets_exit_2`
- `test_provider_step_persists_artifacts_from_output_bundle`
- `test_nonzero_exit_skips_output_bundle_validation`

**Step 2: Run tests to verify red**

Run:
```bash
pytest tests/test_workflow_output_contract_integration.py -k "output_bundle" -v
```
Expected: FAIL.

**Step 3: Implement executor wiring**

Refactor `_apply_expected_outputs_contract` into a generalized helper (name can stay if behavior expands):
- if `expected_outputs` present: existing flow
- if `output_bundle` present: call `validate_output_bundle(...)`
- preserve `persist_artifacts_in_state` behavior
- preserve contract-violation shape (`exit_code=2`, `error.type=contract_violation`)

**Step 4: Run integration tests**

Run:
```bash
pytest tests/test_workflow_output_contract_integration.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add orchestrator/workflow/executor.py tests/test_workflow_output_contract_integration.py
git commit -m "feat: wire output_bundle into executor artifact contract flow"
```

---

### Task 6: Implement `consume_bundle` Materialization with Dataflow Guarantees

**Files:**
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_artifact_dataflow_integration.py`

**Step 1: Add dataflow red tests**

Add tests:
- `test_v13_consume_bundle_writes_resolved_artifacts_json`
- `test_v13_consume_bundle_include_writes_subset_only`
- `test_v13_consume_bundle_not_written_when_consume_contract_fails`

Expected consume bundle JSON shape:
```json
{
  "plan": "docs/plans/plan-a.md",
  "execution_log": "artifacts/work/latest-execution-log.md"
}
```

**Step 2: Run tests to verify red**

Run:
```bash
pytest tests/test_artifact_dataflow_integration.py -k "consume_bundle or v13" -v
```
Expected: FAIL.

**Step 3: Implement executor consume-bundle write path**

In `_enforce_consumes_contract`, after all consumes resolve and before return:
- if `consume_bundle` exists, write JSON file at `consume_bundle.path`
- write selected artifacts from `consume_bundle.include` (or all resolved consumes)
- enforce workspace path safety
- do not alter pointer-materialization behavior for relpath artifacts

**Step 4: Run targeted and full dataflow tests**

Run:
```bash
pytest tests/test_artifact_dataflow_integration.py -k "consume_bundle or scalar or publishes or consumes" -v
pytest tests/test_artifact_dataflow_integration.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add orchestrator/workflow/executor.py tests/test_artifact_dataflow_integration.py
git commit -m "feat: add consume_bundle materialization for resolved artifacts"
```

---

### Task 7: Add v1.3 Example Workflow and Asymmetric Strictness Coverage

**Files:**
- Create: `workflows/examples/backlog_plan_execute_v1_3_json_bundles.yaml`
- Modify: `tests/test_workflow_examples_v0.py`
- Modify: `workflows/examples/README_v0_artifact_contract.md`

**Step 1: Add new example workflow**

Design example with explicit policy:
- `ExecutePlan` / `FixIssues`: `output_capture: text`, flexible logs
- `AssessExecutionCompletion` / `ReviewImplVsPlan`: `output_capture: json`, strict deterministic outputs
- gate control flow based on strict review artifacts, not prose logs

**Step 2: Add runtime red test**

Add test:
- `test_backlog_plan_execute_v1_3_json_bundles_runtime`

Validate:
- example loads
- bundle-derived artifacts publish/consume correctly
- control decision artifact drives branch behavior

**Step 3: Run tests to verify red**

Run:
```bash
pytest tests/test_workflow_examples_v0.py -k "v1_3_json_bundles" -v
```
Expected: FAIL before implementation completeness.

**Step 4: Make test pass and run example suite**

Run:
```bash
pytest tests/test_workflow_examples_v0.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add workflows/examples/backlog_plan_execute_v1_3_json_bundles.yaml tests/test_workflow_examples_v0.py workflows/examples/README_v0_artifact_contract.md
git commit -m "test: add v1.3 json bundle example with strict review gating"
```

---

### Task 8: Update Normative Specs and Acceptance Index

**Files:**
- Modify: `specs/dsl.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Modify: `specs/io.md`

**Step 1: Add DSL fields and gating docs**

Document in `specs/dsl.md`:
- `output_bundle` schema
- `consume_bundle` schema
- v1.3 gating and `expected_outputs` exclusivity

**Step 2: Update versioning table and migration guidance**

Document in `specs/versioning.md`:
- v1.3 now includes JSON bundled deterministic I/O
- asymmetric strictness policy guidance

**Step 3: Add acceptance criteria entries**

In `specs/acceptance/index.md`, add acceptance IDs for:
- loader gating/validation of bundle fields
- runtime `output_bundle` extraction and contract violations
- runtime `consume_bundle` materialization
- strict review artifact gating policy

**Step 4: Run spec-adjacent regression tests**

Run:
```bash
pytest tests/test_loader_validation.py -k "v13 or output_bundle or consume_bundle" -v
pytest tests/test_workflow_examples_v0.py -k "v1_3_json_bundles" -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add specs/dsl.md specs/versioning.md specs/acceptance/index.md specs/io.md
git commit -m "docs: specify v1.3 json bundle deterministic io contracts"
```

---

## Final Verification Checklist

Run:
```bash
pytest tests/test_loader_validation.py -k "v13 or output_bundle or consume_bundle" -v
pytest tests/test_output_contract.py -k "output_bundle" -v
pytest tests/test_workflow_output_contract_integration.py -k "output_bundle" -v
pytest tests/test_artifact_dataflow_integration.py -k "consume_bundle or scalar" -v
pytest tests/test_workflow_examples_v0.py -k "v1_3_json_bundles" -v
pytest tests/test_loader_validation.py -v
pytest tests/test_output_contract.py -v
pytest tests/test_workflow_examples_v0.py -v
```

Expected:
1. New v1.3 bundle tests pass.
2. Existing v1.2 dataflow behavior remains unchanged.
3. Example workflow proves strict review artifacts drive control flow.

