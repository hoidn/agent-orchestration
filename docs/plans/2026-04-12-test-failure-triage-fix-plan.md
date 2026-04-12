# Test Failure Triage Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not create a worktree for this repo; project instructions explicitly prohibit worktrees.

**Goal:** Reduce the current full-suite failure set from 53 failures by fixing the identified root-cause buckets without undoing the typed workflow bundle migration.

**Architecture:** Treat the failures as four independent tracks: test harness migration to `LoadedWorkflowBundle`, v2 scoped-reference runtime correctness, explicit empty `prompt_consumes` preservation, and nanoBragg demo reference provenance. Keep the typed-bundle-only executor contract intact; update stale tests and mocks instead of reintroducing raw dict execution.

**Tech Stack:** Python, pytest, YAML workflow fixtures, orchestrator typed surface/IR/runtime workflow modules, torch-based demo fixtures, subprocess-based reference harness scripts.

---

## Triage Summary

| Bucket | Count | Root Cause | Fix Strategy |
| --- | ---: | --- | --- |
| Typed bundle API test drift | 44 | Older tests and a CLI mock still pass raw `dict` workflows to `WorkflowExecutor` or index `WorkflowLoader.load()` results as dicts. This conflicts with the intentional `LoadedWorkflowBundle` contract. | Test-only migration: load real bundles, use bundle helper materializers for dict-style assertions, and update mocks to return real bundles. |
| v2 `self.steps` scoped reference fallback | 1 | A bound local loop node address can miss the current iteration result and fall back to same-named parent/root presentation keys. | Runtime fix: preserve self-scope node ownership in loop scope and make bound-address resolution fail when an owned scoped node is unavailable. |
| Explicit empty `prompt_consumes` lost | 1 | Typed runtime collapses missing `prompt_consumes` and explicit `prompt_consumes: []` to the same empty tuple, so prompt injection treats an explicit empty allowlist as unspecified. | Runtime fix: carry `None` for unspecified and `()` for explicit empty through surface, IR, runtime step, and test materializers. |
| nanoBragg demo reference/provenance drift | 7 | The accumulation builder still uses a literal tensor table, lacks the single-case CLI expected by tests, hidden case metadata lacks reference provenance, and one design doc misses the expected scoped-contract wording. | Demo script/docs fix: call the reference runner, write requested output paths, regenerate/update metadata, and align doc wording. |

Do not treat the 44 typed-bundle failures as production executor bugs. `WorkflowExecutor` intentionally raises `TypeError` for raw dict workflows, and `tests/test_workflow_executor_characterization.py::test_executor_requires_loaded_workflow_bundle` asserts that contract.

### Task 1: Migrate stale tests and mocks to `LoadedWorkflowBundle`

**Files:**
- Modify: `tests/workflow_bundle_helpers.py`
- Modify: `tests/e2e/test_e2e_multistep_prompted_loop.py`
- Modify: `tests/test_at65_loop_scoping.py`
- Modify: `tests/test_at66_env_literal_semantics.py`
- Modify: `tests/test_at68_resume_force_restart.py`
- Modify: `tests/test_at69_debug_backups.py`
- Modify: `tests/test_at73_prompt_literal_contents.py`
- Modify: `tests/test_cli_observability_config.py`
- Modify: `tests/test_injection_integration.py`
- Modify: `tests/test_retry_behavior.py`
- Modify: `tests/test_retry_integration.py`

- [ ] **Step 1: Reproduce the bundle drift selectors**

Run:

```bash
pytest \
  tests/e2e/test_e2e_multistep_prompted_loop.py::test_multistep_prompt_file_contract \
  tests/test_at65_loop_scoping.py::test_at65_loop_scoped_steps_current_iteration \
  tests/test_at66_env_literal_semantics.py::TestAT66EnvLiteralSemantics::test_at66_env_no_substitution_command \
  tests/test_cli_observability_config.py::test_run_workflow_persists_observability_runtime_config \
  tests/test_injection_integration.py::test_at28_basic_injection \
  tests/test_retry_behavior.py::TestWorkflowRetryExecution::test_at20_timeout_enforcement \
  tests/test_retry_integration.py::TestRetryIntegration::test_at21_command_with_explicit_retries \
  -q
```

Expected: FAIL with `WorkflowExecutor requires a LoadedWorkflowBundle`, `LoadedWorkflowBundle object is not subscriptable`, or `LoadedWorkflowBundle required`.

- [ ] **Step 2: Add one shared test helper for bundle loading**

In `tests/workflow_bundle_helpers.py`, add imports:

```python
from pathlib import Path

import yaml

from orchestrator.loader import WorkflowLoader
```

Add this helper near the other test-only bundle helpers:

```python
def write_workflow_bundle_for_test(
    workspace: Path,
    workflow: dict[str, Any],
    *,
    filename: str = "workflow.yaml",
) -> tuple[LoadedWorkflowBundle, Path]:
    workflow_path = workspace / filename
    workflow_path.write_text(yaml.safe_dump(workflow, sort_keys=False), encoding="utf-8")
    return WorkflowLoader(workspace).load_bundle(workflow_path), workflow_path
```

- [ ] **Step 3: Update executor tests that pass raw workflow dicts**

In the failing test modules, replace direct `WorkflowExecutor(workflow, ...)` calls with loaded bundles:

```python
loaded, workflow_path = write_workflow_bundle_for_test(tmp_path, workflow)
state_manager.initialize(str(workflow_path))
executor = WorkflowExecutor(loaded, tmp_path, state_manager, ...)
```

Keep existing per-test workspace variables when they differ from `tmp_path`.

- [ ] **Step 4: Update dict-style workflow assertions**

For tests that inspect loader output as a dict, use the existing compatibility helpers instead of indexing `LoadedWorkflowBundle`:

```python
from tests.workflow_bundle_helpers import thaw_surface_workflow

loaded = WorkflowLoader(e2e_workspace).load_bundle(workflow_path)
workflow = thaw_surface_workflow(loaded)
provider_steps = [step for step in workflow["steps"] if "provider" in step]
```

For tests that only need workflow metadata, prefer typed fields:

```python
assert loaded.surface.name == "Modified Workflow"
```

- [ ] **Step 5: Update CLI mocks to return real bundles**

In `tests/test_cli_observability_config.py`, replace the dict return from `mock_loader.return_value.load_bundle.return_value` with a real bundle:

```python
mock_loader.return_value.load_bundle.return_value = WorkflowLoader(tmp_path).load_bundle(workflow_file)
```

- [ ] **Step 6: Run migrated module checks**

Run:

```bash
pytest \
  tests/e2e/test_e2e_multistep_prompted_loop.py::test_multistep_prompt_file_contract \
  tests/test_at65_loop_scoping.py \
  tests/test_at66_env_literal_semantics.py \
  tests/test_at68_resume_force_restart.py::test_at68_force_restart_ignores_workflow_changes \
  tests/test_at69_debug_backups.py \
  tests/test_at73_prompt_literal_contents.py \
  tests/test_cli_observability_config.py::test_run_workflow_persists_observability_runtime_config \
  tests/test_injection_integration.py \
  tests/test_retry_behavior.py \
  tests/test_retry_integration.py \
  -q
```

Expected: bundle-related `TypeError` failures are gone. The v2 self-scope failure may still fail until Task 2.

- [ ] **Step 7: Commit**

```bash
git add tests/workflow_bundle_helpers.py \
  tests/e2e/test_e2e_multistep_prompted_loop.py \
  tests/test_at65_loop_scoping.py \
  tests/test_at66_env_literal_semantics.py \
  tests/test_at68_resume_force_restart.py \
  tests/test_at69_debug_backups.py \
  tests/test_at73_prompt_literal_contents.py \
  tests/test_cli_observability_config.py \
  tests/test_injection_integration.py \
  tests/test_retry_behavior.py \
  tests/test_retry_integration.py
git commit -m "test: migrate executor tests to workflow bundles"
```

### Task 2: Fix v2 scoped `self.steps` bound-address fallback

**Files:**
- Modify: `orchestrator/workflow/loops.py`
- Modify: `orchestrator/workflow/executor.py`
- Test: `tests/test_at65_loop_scoping.py`

- [ ] **Step 1: Run the existing failing regression test**

Run:

```bash
pytest tests/test_at65_loop_scoping.py::test_v2_self_refs_do_not_fall_back_to_root_scope -q
```

Expected: FAIL because `Loop[0].Gate` is `completed` instead of `failed`.

- [ ] **Step 2: Preserve explicit loop self-scope ownership**

In `LoopExecutor.build_loop_scope()` in `orchestrator/workflow/loops.py`, always include the current loop's nested node ids when `loop_step` is available. Add metadata alongside the existing result maps:

```python
if isinstance(loop_step, dict):
    self_node_results = self.build_loop_self_node_results(loop_step, iteration_state)
    scope["self_node_results"] = self_node_results
    projection = getattr(self.executor, "projection", None)
    loop_node_id = self.executor._step_id(loop_step)
    loop_projection = None
    if projection is not None:
        loop_projection = projection.repeat_until_nodes.get(loop_node_id)
        if loop_projection is None:
            loop_projection = projection.for_each_nodes.get(loop_node_id)
    if loop_projection is not None:
        scope["self_node_ids"] = {
            node_id: True
            for node_id in loop_projection.nested_presentation_keys
        }
```

If static typing complains, widen the local `scope` type to a looser mapping shape such as `Dict[str, Mapping[str, Any]]`.

- [ ] **Step 3: Make `_result_for_node_id()` fail on unavailable owned scoped nodes**

In `WorkflowExecutor._result_for_node_id()` in `orchestrator/workflow/executor.py`, check ownership maps before presentation-key fallback:

```python
if isinstance(scope, dict):
    for ids_key, results_key in (
        ("self_node_ids", "self_node_results"),
        ("parent_node_ids", "parent_node_results"),
    ):
        node_ids = scope.get(ids_key)
        if isinstance(node_ids, Mapping) and node_id in node_ids:
            results = scope.get(results_key)
            if isinstance(results, Mapping):
                candidate = results.get(node_id)
                if isinstance(candidate, dict):
                    return candidate
            raise ReferenceResolutionError(
                f"Bound address target step '{node_id}' is unavailable"
            )
```

Keep the existing top-level presentation-key fallback for unscoped/top-level bound addresses.

- [ ] **Step 4: Run focused scoped-reference checks**

Run:

```bash
pytest \
  tests/test_at65_loop_scoping.py::test_v2_self_refs_do_not_fall_back_to_root_scope \
  tests/test_at65_loop_scoping.py::test_v2_nested_steps_execute_with_scoped_refs_inside_for_each \
  -q
```

Expected: both PASS.

- [ ] **Step 5: Run the full AT-65 module**

Run:

```bash
pytest tests/test_at65_loop_scoping.py -q
```

Expected: PASS after Task 1 and this runtime fix.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/workflow/loops.py orchestrator/workflow/executor.py tests/test_at65_loop_scoping.py
git commit -m "fix: preserve loop self scope for bound references"
```

### Task 3: Preserve explicit empty `prompt_consumes`

**Files:**
- Modify: `orchestrator/workflow/surface_ast.py`
- Modify: `orchestrator/workflow/elaboration.py`
- Modify: `orchestrator/workflow/executable_ir.py`
- Modify: `orchestrator/workflow/runtime_step.py`
- Modify: `tests/workflow_bundle_helpers.py`
- Test: `tests/test_prompt_contract_injection.py`

- [ ] **Step 1: Run the existing failing prompt-consumes test**

Run:

```bash
pytest tests/test_prompt_contract_injection.py::test_prompt_consumes_empty_list_injects_no_consumed_artifacts_block -q
```

Expected: FAIL because a `## Consumed Artifacts` block is injected.

- [ ] **Step 2: Differentiate unspecified vs explicit empty at the surface**

In `orchestrator/workflow/surface_ast.py`, change:

```python
prompt_consumes: tuple[Any, ...] = ()
```

to:

```python
prompt_consumes: Optional[tuple[Any, ...]] = None
```

In `orchestrator/workflow/elaboration.py`, set `prompt_consumes` only when the authored key exists:

```python
prompt_consumes=(
    _frozen_sequence(step["prompt_consumes"])
    if kind is SurfaceStepKind.PROVIDER and "prompt_consumes" in step
    else None
),
```

- [ ] **Step 3: Preserve the distinction through IR and runtime step lookup**

In `orchestrator/workflow/executable_ir.py`, change `ProviderStepConfig.prompt_consumes` to:

```python
prompt_consumes: Optional[tuple[Any, ...]] = None
```

In `orchestrator/workflow/runtime_step.py`, return explicit empty lists instead of omitting them:

```python
if key == "prompt_consumes" and config.prompt_consumes is not None:
    return thaw_runtime_value(config.prompt_consumes)
```

- [ ] **Step 4: Update test materializers to keep explicit empty lists**

In `tests/workflow_bundle_helpers.py`, update provider rendering to include `prompt_consumes` when it is not `None`:

```python
if config.prompt_consumes is not None:
    step["prompt_consumes"] = _thaw(config.prompt_consumes)
```

For surface rendering, use the same `is not None` rule:

```python
if step.prompt_consumes is not None:
    payload["prompt_consumes"] = _thaw(step.prompt_consumes)
```

- [ ] **Step 5: Run prompt injection checks**

Run:

```bash
pytest \
  tests/test_prompt_contract_injection.py::test_prompt_consumes_empty_list_injects_no_consumed_artifacts_block \
  tests/test_prompt_contract_injection.py \
  -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/workflow/surface_ast.py \
  orchestrator/workflow/elaboration.py \
  orchestrator/workflow/executable_ir.py \
  orchestrator/workflow/runtime_step.py \
  tests/workflow_bundle_helpers.py \
  tests/test_prompt_contract_injection.py
git commit -m "fix: preserve explicit empty prompt consumes"
```

### Task 4: Restore nanoBragg accumulation reference provenance

**Files:**
- Modify: `scripts/demo/build_nanobragg_reference_cases.py`
- Modify: `orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/cases.json`
- Modify: `docs/plans/2026-03-05-workflow-demo-design.md`
- Possibly update generated `.pt` fixtures under `orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/` if the reference-runner output changes them.

- [ ] **Step 1: Reproduce the demo failures**

Run:

```bash
pytest \
  tests/test_demo_nanobragg_reference_generation.py \
  tests/test_demo_nanobragg_reference_provenance.py \
  tests/test_demo_task_nanobragg_alignment.py \
  -q
```

Expected: FAIL on missing output-path write, literal `REFERENCE_TENSORS`, missing case provenance fields, missing `RUN_REFERENCE`, and missing `scoped contract` wording in the design doc.

- [ ] **Step 2: Rewrite the accumulation builder to use the reference runner**

In `scripts/demo/build_nanobragg_reference_cases.py`, follow the existing pattern in `scripts/demo/build_nanobragg_entrypoint_cases.py`:

```python
import argparse
import json
import subprocess
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "orchestrator" / "demo" / "evaluators" / "fixtures" / "nanobragg_accumulation"
SEED_ROOT = ROOT / "examples" / "demo_task_nanobragg_accumulation_port"
RUN_REFERENCE = ROOT / "scripts" / "demo" / "nanobragg_reference" / "run_reference_case.py"


def _run_reference(fixture_path: Path) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, str(RUN_REFERENCE), str(fixture_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _tensor_from_payload(payload: dict[str, object]) -> torch.Tensor:
    return torch.tensor(payload["flat_data"], dtype=torch.float64).reshape(payload["shape"])
```

Add single-case mode:

```python
def _run_single_case(case_id: str, fixture_path: Path, output_path: Path) -> int:
    payload = _run_reference(fixture_path)
    if payload.get("case_id") != case_id:
        raise ValueError(f"Expected case_id {case_id}, got {payload.get('case_id')}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(_tensor_from_payload(payload), output_path)
    return 0
```

Add argparse support for the test-facing CLI:

```python
parser.add_argument("--case-id")
parser.add_argument("--fixture-path", type=Path)
parser.add_argument("--output-path", type=Path)
```

When all three are present, call `_run_single_case()` and return without rewriting `cases.json`.

- [ ] **Step 3: Update batch mode to persist provenance**

In batch mode, for each case in `cases.json`:

```python
payload = _run_reference(input_path)
tensor = _tensor_from_payload(payload)
torch.save(tensor, output_path)
case["reference_method"] = payload["reference_method"]
case["reference_source"] = payload["reference_source"]
case["reference_snapshot"] = payload["reference_snapshot"]
```

Write the updated metadata back to `orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/cases.json`.

- [ ] **Step 4: Regenerate accumulation fixture metadata**

Run:

```bash
python scripts/demo/build_nanobragg_reference_cases.py
```

Expected: `cases.json` contains `reference_method`, `reference_source`, and `reference_snapshot` for every case. Inspect any `.pt` diffs before committing; include them only if the reference-runner output changed fixture tensors.

- [ ] **Step 5: Align design doc wording**

In `docs/plans/2026-03-05-workflow-demo-design.md`, add the exact phrase `scoped contract` in the relevant review/demo design section without changing the intended meaning. Keep it as user-facing repo documentation, not test-only wording.

- [ ] **Step 6: Run demo checks**

Run:

```bash
pytest \
  tests/test_demo_nanobragg_reference_generation.py \
  tests/test_demo_nanobragg_reference_provenance.py \
  tests/test_demo_task_nanobragg_alignment.py \
  -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/demo/build_nanobragg_reference_cases.py \
  orchestrator/demo/evaluators/fixtures/nanobragg_accumulation/cases.json \
  docs/plans/2026-03-05-workflow-demo-design.md
git status --short
git commit -m "fix: restore nanobragg reference provenance"
```

Add changed `.pt` fixtures to the commit only if Step 4 actually changed them and the diff is expected.

### Task 5: Final verification

**Files:**
- No planned edits.

- [ ] **Step 1: Run focused regression buckets**

Run:

```bash
pytest \
  tests/e2e/test_e2e_multistep_prompted_loop.py::test_multistep_prompt_file_contract \
  tests/test_at65_loop_scoping.py \
  tests/test_at66_env_literal_semantics.py \
  tests/test_at68_resume_force_restart.py::test_at68_force_restart_ignores_workflow_changes \
  tests/test_at69_debug_backups.py \
  tests/test_at73_prompt_literal_contents.py \
  tests/test_cli_observability_config.py::test_run_workflow_persists_observability_runtime_config \
  tests/test_injection_integration.py \
  tests/test_prompt_contract_injection.py::test_prompt_consumes_empty_list_injects_no_consumed_artifacts_block \
  tests/test_retry_behavior.py \
  tests/test_retry_integration.py \
  tests/test_demo_nanobragg_reference_generation.py \
  tests/test_demo_nanobragg_reference_provenance.py \
  tests/test_demo_task_nanobragg_alignment.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run the full suite under tmux**

Run:

```bash
pytest -q --tb=short -ra
```

Expected: no failures. E2E tests may remain skipped unless `ORCHESTRATE_E2E` is set; do not convert skipped provider E2E tests into required checks unless the task specifically enables real provider execution.

- [ ] **Step 3: Verify generated workflow prompt map stayed current**

Run:

```bash
python scripts/workflow_prompt_map.py --check
pytest tests/test_workflow_prompt_map.py -q
```

Expected: PASS.

- [ ] **Step 4: Record final status**

Run:

```bash
git status --short
git log --oneline -5
```

Expected: clean working tree, with the task commits at the top.
