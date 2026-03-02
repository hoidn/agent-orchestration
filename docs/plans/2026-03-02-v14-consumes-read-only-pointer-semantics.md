# v1.4 Consumes Read-Only Pointer Semantics Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate consume-time pointer-file mutation for relpath artifacts so consumed dataflow is read-only and cannot clobber step-owned output pointers.

**Architecture:** Introduce DSL `version: "1.4"` with principled consume semantics: resolve consumed artifact versions into in-memory state and optional `consume_bundle`, but never rewrite artifact registry pointer files during consume preflight. Preserve legacy behavior for `1.2`/`1.3` to avoid breaking existing workflows, and document migration for command steps that need deterministic consumed values via `consume_bundle`.

**Tech Stack:** Python (`orchestrator/loader.py`, `orchestrator/workflow/executor.py`), YAML DSL specs (`specs/dsl.md`, `specs/versioning.md`), authoring guidance (`docs/workflow_drafting_guide.md`), pytest integration/unit tests.

---

## Design Decisions (Normative)

1. Pointer ownership is producer-only.
- Pointer files declared in top-level `artifacts.*.pointer` are write-owned by producer steps through `expected_outputs`/`publishes`.
- Consume preflight must not mutate these pointer files in v1.4.

2. Versioned rollout.
- `1.2` and `1.3` keep current behavior for compatibility.
- `1.4` switches relpath consumes to read-only pointer semantics.

3. Dataflow remains deterministic without pointer writes.
- Consume resolution still validates publication freshness and type contracts.
- Resolved values still flow through:
  - `state._resolved_consumes[<step_name>]`
  - provider prompt consumed-artifact injection
  - optional `consume_bundle` materialization (recommended for command steps)

4. Command-step migration path.
- In `1.4`, command steps that need consumed relpath values should read from `consume_bundle` JSON instead of reading registry pointer files.

5. Non-goals for this slice.
- No changes to `publishes` semantics.
- No new consume policy names beyond `latest_successful`.
- No overhaul of prompt injection format.

---

### Task 1: Add Red Tests for v1.4 Non-Mutating Consumes

**Files:**
- Modify: `tests/test_artifact_dataflow_integration.py`

**Step 1: Add failing regression test for pointer clobber prevention**

Add a test that reproduces the aliasing bug shape:
- publish `execution_log` to `artifacts/work/c0-execute.md`
- write a new destination pointer `state/execution_log_path.txt = artifacts/work/c2-fix.md`
- run a consuming step (`consumes: execution_log`) that reads the pointer path
- assert pointer remains `artifacts/work/c2-fix.md` under `version: "1.4"`

Example workflow fragment:

```python
workflow = {
    "version": "1.4",
    "name": "consume-no-clobber-v14",
    "artifacts": _artifact_registry(),
    "steps": [
        _publish_step("ExecutePlan", "artifacts/work/c0-execute.md"),
        {
            "name": "PrepareFixPointer",
            "command": [
                "bash",
                "-lc",
                "printf 'artifacts/work/c2-fix.md\\n' > state/execution_log_path.txt",
            ],
        },
        {
            "name": "FixIssues",
            "consumes": [{
                "artifact": "execution_log",
                "producers": ["ExecutePlan"],
                "policy": "latest_successful",
                "freshness": "any",
            }],
            "command": ["bash", "-lc", "cat state/execution_log_path.txt"],
        },
    ],
}
```

Expected assertion:

```python
assert state["steps"]["FixIssues"]["output"].strip() == "artifacts/work/c2-fix.md"
```

**Step 2: Add a compatibility test for v1.3**

Add/adjust test that proves `1.3` still rewrites pointer on consume (legacy behavior preserved).

**Step 3: Run red tests**

Run:
```bash
pytest tests/test_artifact_dataflow_integration.py -k "consume and (v14 or clobber or latest_successful)" -v
```

Expected: new v1.4 test fails before implementation.

**Step 4: Commit test scaffolding**

```bash
git add tests/test_artifact_dataflow_integration.py
git commit -m "test(dataflow): add v1.4 consume pointer non-mutation regression"
```

---

### Task 2: Enable DSL v1.4 in Loader and Version Gates

**Files:**
- Modify: `orchestrator/loader.py`
- Modify: `tests/test_loader_validation.py`

**Step 1: Add failing loader tests for v1.4 acceptance**

Add tests asserting:
- `version: "1.4"` loads as supported.
- `artifacts` / `publishes` / `consumes` accepted in `1.4`.
- `output_bundle` / `consume_bundle` accepted in `1.4` (currently gated to exactly `1.3`).

**Step 2: Run red loader tests**

Run:
```bash
pytest tests/test_loader_validation.py -k "1.4 or v13_output_bundle_requires_version_1_3 or v13_consume_bundle_requires_version_1_3" -v
```

Expected: fails until loader gates are updated.

**Step 3: Implement loader gate changes**

Update:
- `SUPPORTED_VERSIONS` to include `"1.4"`.
- Top-level artifacts version checks from `{1.2, 1.3}` to `{1.2, 1.3, 1.4}`.
- Step gates for `publishes` / `consumes` / prompt consume controls to include `1.4`.
- `output_bundle` / `consume_bundle` gate from `version == "1.3"` to `version in {"1.3", "1.4"}`.

**Step 4: Re-run loader tests**

Run:
```bash
pytest tests/test_loader_validation.py -k "1.4 or output_bundle or consume_bundle or consumes" -v
pytest tests/test_loader_validation.py -v
```

Expected: pass.

**Step 5: Commit loader updates**

```bash
git add orchestrator/loader.py tests/test_loader_validation.py
git commit -m "feat(loader): add DSL v1.4 support and gating"
```

---

### Task 3: Implement v1.4 Read-Only Consume Semantics in Executor

**Files:**
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_artifact_dataflow_integration.py`

**Step 1: Add failing behavior pin test (if not already in Task 1)**

Ensure there is a test that fails specifically because consume preflight currently rewrites `state/execution_log_path.txt`.

**Step 2: Implement version-aware consume behavior**

In `_enforce_consumes_contract(...)`, for `artifact_kind == "relpath"`:
- keep value/type validation as-is
- for `version in {"1.2", "1.3"}` keep legacy pointer write
- for `version == "1.4"` skip pointer-file write entirely

Suggested helper:

```python
def _consumes_materialize_relpath_pointer(self) -> bool:
    return self.workflow.get("version") in {"1.2", "1.3"}
```

And gate:

```python
if artifact_kind == "relpath":
    ...
    if self._consumes_materialize_relpath_pointer():
        pointer_path.write_text(f"{selected_value}\n")
```

**Step 3: Ensure consume bookkeeping remains unchanged**

Keep:
- `artifact_consumes` updates
- `_resolved_consumes` updates
- `consume_bundle` behavior

No regressions in freshness checks.

**Step 4: Run focused tests**

Run:
```bash
pytest tests/test_artifact_dataflow_integration.py -k "consume" -v
pytest tests/test_prompt_contract_injection.py -k "consumes" -v
```

Expected: v1.4 test passes; existing consume tests remain green.

**Step 5: Commit executor behavior**

```bash
git add orchestrator/workflow/executor.py tests/test_artifact_dataflow_integration.py
git commit -m "feat(executor): make v1.4 relpath consumes read-only for pointer files"
```

---

### Task 4: Document v1.4 Pointer Ownership and Migration

**Files:**
- Modify: `specs/dsl.md`
- Modify: `specs/versioning.md`
- Modify: `docs/workflow_drafting_guide.md`

**Step 1: Update DSL semantics text**

In `specs/dsl.md` dataflow section:
- replace unconditional pointer materialization language with versioned behavior:
  - `1.2/1.3`: relpath consumes may materialize selected value to pointer
  - `1.4`: relpath consumes are read-only; no pointer mutation

**Step 2: Update versioning**

In `specs/versioning.md` add v1.4 section:
- pointer ownership change
- backward compatibility for old versions
- migration recommendation: command steps should use `consume_bundle` for deterministic consumed values

**Step 3: Update drafting guidance**

In `docs/workflow_drafting_guide.md`:
- add rule: do not rely on consume-time pointer rewrites in v1.4
- show preferred command-step pattern using `consume_bundle` JSON

Example guidance snippet:

```yaml
consume_bundle:
  path: state/consumes/fix_issues.json
```

and command reads JSON key instead of pointer file.

**Step 4: Commit docs**

```bash
git add specs/dsl.md specs/versioning.md docs/workflow_drafting_guide.md
git commit -m "docs(dsl): define v1.4 read-only consume pointer semantics"
```

---

### Task 5: End-to-End Regression and Safety Verification

**Files:**
- Modify if needed from failures discovered in this task.

**Step 1: Run targeted regression suite**

Run:
```bash
pytest tests/test_artifact_dataflow_integration.py -v
pytest tests/test_loader_validation.py -k "1.4 or consumes or output_bundle or consume_bundle" -v
pytest tests/test_prompt_contract_injection.py -k "consumes" -v
```

Expected: PASS.

**Step 2: Run wider workflow suite**

Run:
```bash
pytest tests/test_workflow_output_contract_integration.py -v
pytest tests/test_resume_command.py -v
```

Expected: PASS; no regressions in state persistence or contract handling.

**Step 3: Final commit for follow-up fixes**

```bash
git add -A
git commit -m "test: finalize v1.4 consumes non-mutation regressions"
```

---

## Acceptance Criteria

1. New `version: "1.4"` workflows no longer have consume-time pointer mutation for `kind: relpath` artifacts.
2. Existing `1.2`/`1.3` workflows retain current behavior (no silent break).
3. The pointer-clobber regression scenario passes under v1.4.
4. Consumed artifacts still appear correctly in provider prompt injection and `consume_bundle`.
5. Specs and drafting guide explicitly document ownership semantics and migration path.

## Risks and Mitigations

- Risk: Hidden workflows depend on pointer mutation side-effect.
  - Mitigation: versioned rollout; legacy semantics unchanged.

- Risk: Command consumers in v1.4 may read stale pointer files if they never migrate.
  - Mitigation: docs mandate `consume_bundle` for command steps needing consumed values.

- Risk: Loader gate drift (1.4 acceptance inconsistent across features).
  - Mitigation: add explicit loader tests for each gated feature.

