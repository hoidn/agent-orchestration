# Pytest Failure Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the current `pytest -n auto tests` failure clusters without weakening the new Workflow Lisp lint, route-readiness, or value-flow evidence gates.

**Architecture:** Treat the failures as three independent gate-alignment problems, not as one broad regression: command-boundary fixtures must carry required G0 retirement metadata, the route-readiness registry must cover newly landed `.orc` surfaces, and value-flow census tests must land with their implementation and checked fixture. Keep existing in-progress workflow-generated docs separate from the test repair unless explicitly requested.

**Tech Stack:** Python 3.13 test environment from `/home/ollie/miniconda3/bin`, pytest/xdist, Workflow Lisp compiler tests, JSON manifests, checked-in route-readiness and migration evidence fixtures.

---

## Current Failure Evidence

The requested command was run from the repo root in tmux:

```bash
pytest -n auto tests
```

The tmux shell resolved to:

```bash
/home/ollie/miniconda3/bin/pytest
Python 3.13.9
```

Observed result:

```text
193 failed, 3114 passed, 11 skipped in 46.05s
```

Do not use `.pytest_cache/v/cache/lastfailed` as the sole source of truth: it contained stale entries for renamed or removed tests. Use fresh focused reruns with `/home/ollie/miniconda3/bin/pytest`.

## File Responsibility Map

- `orchestrator/workflow_lisp/command_boundaries.py`: owns required G0 retirement metadata enforcement. Do not weaken this gate.
- `orchestrator/workflow_lisp/value_flow_census.py`: untracked implementation module currently present in the working tree; should either be completed and tracked or removed with its tests.
- `orchestrator/workflow_lisp/build.py`: already imports and consumes value-flow census support in the dirty workspace.
- `docs/workflow_lisp_route_readiness_registry.json`: checked-in route registry; missing entries for seven committed `.orc` surfaces.
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json`: canonical command-boundary metadata source for the Design Delta parent drain.
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.value_flow_census.json`: missing checked fixture expected by dirty build-artifact tests.
- `tests/workflow_lisp_characterization.py`: parses characterization command-boundary manifests; currently creates bare `ExternalToolBinding` values.
- `tests/test_workflow_lisp_wcc_m*.py`, `tests/test_workflow_lisp_source_map.py`, `tests/test_workflow_semantic_ir.py`, `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`, `tests/test_loader_validation.py`: contain direct command-boundary helpers that need canonical metadata-bearing bindings.
- `tests/test_workflow_lisp_value_flow_census.py`: untracked tests for the untracked value-flow census module.
- `tests/test_workflow_lisp_build_artifacts.py`, `tests/test_workflow_lisp_migration_parity.py`: dirty tests expecting value-flow census build/parity behavior.

## Guardrails

- Do not revert unrelated dirty workflow/run-output files.
- Do not weaken `command_adapter_missing_contract`.
- Do not make G0 metadata optional for Design Delta helper names.
- Do not mark route-readiness entries as current unless they have real evidence selectors.
- Do not stage generated design-gap directories unless this repair explicitly uses them.
- Use `/home/ollie/miniconda3/bin/pytest` for focused reruns so results match the full-suite environment.

## Task 0: Snapshot And Stabilize The Worktree

**Files:**
- Read only: working tree
- No commit in this task

- [ ] **Step 1: Record dirty state**

Run:

```bash
git status --short
git diff --stat
git ls-files -d -m -o --exclude-standard | sort
```

Expected: dirty files include the in-progress provider-lane docs, untracked design-gap directories, untracked `orchestrator/workflow_lisp/value_flow_census.py`, and untracked `tests/test_workflow_lisp_value_flow_census.py`.

- [ ] **Step 2: Reconfirm the three representative failures**

Run:

```bash
/home/ollie/miniconda3/bin/pytest -q tests/test_workflow_lisp_wcc_m5.py::test_compile_stage3_module_defaults_to_wcc_schema_2 -vv
/home/ollie/miniconda3/bin/pytest -q tests/test_workflow_lisp_route_readiness.py::test_checked_in_registry_loads_and_validates -vv
/home/ollie/miniconda3/bin/pytest -q tests/test_workflow_lisp_value_flow_census.py -x -vv
```

Expected failures:

- `command_adapter_missing_contract` for bare `validate_review_findings_v1`.
- `route_readiness_surface_missing` for seven `.orc` paths.
- value-flow census module/fixture failures until the untracked module and checked fixture are completed.

## Task 1: Centralize Metadata-Bearing G0 Command Bindings

**Files:**
- Create: `tests/workflow_lisp_command_boundaries.py`
- Modify: `tests/workflow_lisp_characterization.py`
- Modify focused test modules that directly create `validate_review_findings_v1` bindings

- [ ] **Step 1: Add a failing helper-usage test**

Add to `tests/test_workflow_lisp_wcc_m5.py` or a new focused test module:

```python
def test_design_delta_review_findings_fixture_binding_carries_g0_metadata():
    from tests.workflow_lisp_command_boundaries import validate_review_findings_v1_binding

    binding = validate_review_findings_v1_binding()

    assert binding.retirement_class == "validation"
    assert binding.retirement_label == "keep_bridge"
    assert binding.bridge_owner == "std/phase"
    assert binding.evidence_refs
```

Run:

```bash
/home/ollie/miniconda3/bin/pytest -q tests/test_workflow_lisp_wcc_m5.py::test_design_delta_review_findings_fixture_binding_carries_g0_metadata -vv
```

Expected before implementation: import failure for `tests.workflow_lisp_command_boundaries`.

- [ ] **Step 2: Add canonical test helper**

Create `tests/workflow_lisp_command_boundaries.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from orchestrator.workflow_lisp.workflows import ExternalToolBinding


def validate_review_findings_v1_binding() -> ExternalToolBinding:
    return ExternalToolBinding(
        name="validate_review_findings_v1",
        stable_command=(
            "python",
            "-m",
            "orchestrator.workflow_lisp.adapters.validate_review_findings_v1",
        ),
        retirement_class="validation",
        retirement_label="keep_bridge",
        replacement_surface="typed review findings validation bridge",
        bridge_owner="std/phase",
        expiry_condition=(
            "retain until typed review-findings validation parity replaces the command bridge"
        ),
        evidence_refs=("validate_review_findings_v1",),
    )


def run_checks_binding() -> ExternalToolBinding:
    return ExternalToolBinding(
        name="run_checks",
        stable_command=("python", "scripts/run_checks.py"),
    )


def external_tool_binding_from_manifest(name: str, payload: Mapping[str, Any]) -> ExternalToolBinding:
    stable_command = tuple(str(token) for token in payload.get("stable_command", ()))
    kwargs: dict[str, Any] = {}
    for key in (
        "retirement_class",
        "retirement_label",
        "replacement_surface",
        "bridge_owner",
        "expiry_condition",
        "retirement_status",
    ):
        value = payload.get(key)
        if value is not None:
            kwargs[key] = str(value)
    evidence_refs = payload.get("evidence_refs")
    if evidence_refs is not None:
        kwargs["evidence_refs"] = tuple(str(item) for item in evidence_refs)
    return ExternalToolBinding(name=name, stable_command=stable_command, **kwargs)
```

- [ ] **Step 3: Update characterization manifest parsing**

In `tests/workflow_lisp_characterization.py`, replace direct `ExternalToolBinding(name=name, stable_command=...)` construction with `external_tool_binding_from_manifest(name, payload)`.

If characterization manifests lack metadata for `validate_review_findings_v1`, update `tests/fixtures/workflow_lisp/characterization/manifest.json` entries for that boundary to include the same G0 fields as `design_delta_parent_drain.commands.json`.

- [ ] **Step 4: Replace direct bare bindings in focused fixture helpers**

Use the helper for `validate_review_findings_v1` in at least these files:

```text
tests/test_workflow_lisp_wcc_m1.py
tests/test_workflow_lisp_wcc_m4.py
tests/test_workflow_lisp_wcc_m5.py
tests/test_workflow_lisp_source_map.py
tests/test_workflow_semantic_ir.py
tests/test_loader_validation.py
tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py
tests/test_workflow_lisp_build_artifacts.py
```

Do not change unrelated `run_checks` bindings unless needed for helper consistency.

- [ ] **Step 5: Verify the lint still fails for a truly bare Design Delta helper**

Run an existing negative test or add one in `tests/test_workflow_lisp_command_adapters.py`:

```python
def test_design_delta_g0_helper_without_retirement_metadata_is_rejected():
    from orchestrator.workflow_lisp.command_boundaries import build_command_boundary_environment
    from orchestrator.workflow_lisp.workflows import ExternalToolBinding

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_command_boundary_environment({
            "validate_review_findings_v1": ExternalToolBinding(
                name="validate_review_findings_v1",
                stable_command=(
                    "python",
                    "-m",
                    "orchestrator.workflow_lisp.adapters.validate_review_findings_v1",
                ),
            )
        })

    assert excinfo.value.diagnostics[0].code == "command_adapter_missing_contract"
```

- [ ] **Step 6: Focused verification**

Run:

```bash
/home/ollie/miniconda3/bin/pytest -q \
  tests/test_workflow_lisp_wcc_m5.py::test_compile_stage3_module_defaults_to_wcc_schema_2 \
  tests/test_workflow_lisp_wcc_m4.py::test_wcc_m4_hoists_effectful_match_arm_steps_by_structure_not_workflow_name \
  tests/test_workflow_lisp_source_map.py::test_source_map_records_generated_paths_inside_nested_branch_scopes \
  tests/test_workflow_semantic_ir.py::test_frontend_build_semantic_ir_projects_generated_snapshot_and_pointer_effects \
  -vv
```

Expected: no `command_adapter_missing_contract` caused by `validate_review_findings_v1`.

- [ ] **Step 7: Commit**

```bash
git add tests/workflow_lisp_command_boundaries.py \
  tests/workflow_lisp_characterization.py \
  tests/test_workflow_lisp_wcc_m1.py \
  tests/test_workflow_lisp_wcc_m4.py \
  tests/test_workflow_lisp_wcc_m5.py \
  tests/test_workflow_lisp_source_map.py \
  tests/test_workflow_semantic_ir.py \
  tests/test_loader_validation.py \
  tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/fixtures/workflow_lisp/characterization/manifest.json
git commit -m "Align Workflow Lisp tests with G0 command metadata"
```

Adjust the staged file list to the actual touched files.

## Task 2: Update Route-Readiness Registry Coverage

**Files:**
- Modify: `docs/workflow_lisp_route_readiness_registry.json`
- Test: `tests/test_workflow_lisp_route_readiness.py`

- [ ] **Step 1: Capture the current missing paths**

Run:

```bash
/home/ollie/miniconda3/bin/python - <<'PY'
from pathlib import Path
from orchestrator.workflow_lisp.route_readiness import (
    load_route_readiness_registry,
    validate_route_readiness_registry,
)
root = Path.cwd()
registry = load_route_readiness_registry(root / "docs/workflow_lisp_route_readiness_registry.json")
validation = validate_route_readiness_registry(registry, root)
for issue in validation.issues:
    print(issue.code, issue.path)
PY
```

Expected missing paths:

```text
tests/fixtures/workflow_lisp/valid/design_delta_projection_runtime.orc
tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/projections.orc
tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/transitions.orc
workflows/library/lisp_frontend_design_delta/projections.orc
workflows/library/lisp_frontend_design_delta/runtime_transition_fixture.orc
workflows/library/lisp_frontend_design_delta/runtime_view_fixture.orc
workflows/library/lisp_frontend_design_delta/transitions.orc
```

- [ ] **Step 2: Add registry entries**

For each path, add a registry surface with:

```json
{
  "surface_id": "<dot-normalized path without .orc>",
  "path": "<path>",
  "surface_kind": "workflow_library",
  "route_label": "wcc_default",
  "readiness_label": "leaf_runtime_candidate",
  "lowering_route": "wcc_m4",
  "lowering_schema_version": 2,
  "copy_safety": "preferred_current_guidance",
  "evidence": ["<real pytest selector that compiles/smokes this surface>"]
}
```

Use `test_fixture` / `test_evidence_only` for fixture-only paths under `tests/fixtures/**`.

Do not invent evidence selectors. Use existing focused tests from:

```text
tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py
tests/test_workflow_lisp_build_artifacts.py
tests/test_workflow_lisp_resource_stdlib.py
tests/test_workflow_lisp_materialize_view_runtime.py
```

- [ ] **Step 3: Verify registry validation**

Run:

```bash
/home/ollie/miniconda3/bin/pytest -q tests/test_workflow_lisp_route_readiness.py::test_checked_in_registry_loads_and_validates -vv
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add docs/workflow_lisp_route_readiness_registry.json
git commit -m "Register new Workflow Lisp route surfaces"
```

## Task 3: Complete Or Park Value-Flow Census Work

**Files if completing:**
- Add: `orchestrator/workflow_lisp/value_flow_census.py`
- Add: `tests/test_workflow_lisp_value_flow_census.py`
- Add: `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.value_flow_census.json`
- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_migration_parity.py`

**Files if parking:**
- Remove or stash untracked value-flow census tests/module.
- Revert dirty test/build expectations that reference value-flow census.

Recommended path: complete and track it, because `build.py` already imports and uses the module in the dirty workspace.

- [ ] **Step 1: Run value-flow unit tests**

Run:

```bash
/home/ollie/miniconda3/bin/pytest -q tests/test_workflow_lisp_value_flow_census.py -vv
```

Expected before completion: failures identify missing or incomplete implementation.

- [ ] **Step 2: Finish module API**

Ensure `orchestrator/workflow_lisp/value_flow_census.py` exports at least:

```python
VALUE_FLOW_CENSUS_SCHEMA_VERSION = "workflow_lisp_private_runtime_value_flow_census.v1"
VALUE_FLOW_CENSUS_REPORT_SCHEMA_VERSION = "workflow_lisp_private_runtime_value_flow_census_report.v1"

def load_value_flow_census(path: Path) -> dict[str, Any]: ...

def reconcile_value_flow_census(
    *,
    census: Mapping[str, Any],
    checked_census_path: Path,
    checked_census_sha256: str,
    boundary_projection: Mapping[str, Any],
    semantic_ir: Mapping[str, Any] | None = None,
    source_map: Mapping[str, Any] | None = None,
) -> dict[str, Any]: ...
```

Match the actual `build.py` call signature before editing tests.

- [ ] **Step 3: Add checked census fixture**

Create `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.value_flow_census.json`.

Minimum requirements from existing dirty tests:

- `schema_version`
- `target_family`
- `source_design`
- `coverage.required_source_kinds`
- `workflow_rows` or `rows`, according to the module contract
- rows including:
  - `drain.bridge.manifest_path`
  - `drain.generated.state_root`
  - `work_item.pointer.selection_bundle_path`

Each row must declare:

```json
{
  "row_id": "...",
  "workflow_surface": "...",
  "source_kind": "...",
  "symbol_or_field": "...",
  "path_or_contract": "...",
  "plumbing_class": "...",
  "boundary_authority_class": "...",
  "track_owner": "...",
  "current_consumer": "...",
  "semantic_owner": "...",
  "source_evidence": [],
  "replacement_target": null,
  "command_boundary": null,
  "bridge": null,
  "notes": ""
}
```

- [ ] **Step 4: Verify unit and build-artifact tests**

Run:

```bash
/home/ollie/miniconda3/bin/pytest -q tests/test_workflow_lisp_value_flow_census.py -vv
/home/ollie/miniconda3/bin/pytest -q tests/test_workflow_lisp_build_artifacts.py -k "value_flow_census" -vv
```

Expected: value-flow tests pass or fail only on a specific stale-row/content assertion that points to the fixture.

- [ ] **Step 5: Verify migration-parity integration**

Run:

```bash
/home/ollie/miniconda3/bin/pytest -q tests/test_workflow_lisp_migration_parity.py -k "value_flow_census or design_delta_parent_drain" -vv
```

- [ ] **Step 6: Commit**

```bash
git add orchestrator/workflow_lisp/value_flow_census.py \
  tests/test_workflow_lisp_value_flow_census.py \
  workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.value_flow_census.json \
  orchestrator/workflow_lisp/build.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_migration_parity.py
git commit -m "Add Workflow Lisp value-flow census gate"
```

Adjust the staged file list to the actual touched files.

## Task 4: Re-run Workflow Lisp Failure Cluster

**Files:**
- No new files unless failures expose a narrow bug

- [ ] **Step 1: Run the high-signal cluster**

Run:

```bash
/home/ollie/miniconda3/bin/pytest -q \
  tests/test_workflow_lisp_wcc_m5.py \
  tests/test_workflow_lisp_wcc_m4.py \
  tests/test_workflow_lisp_wcc_characterization.py \
  tests/test_workflow_lisp_source_map.py \
  tests/test_workflow_semantic_ir.py \
  tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_route_readiness.py \
  tests/test_workflow_lisp_value_flow_census.py \
  -vv
```

Expected: no failures from the three root-cause classes above.

- [ ] **Step 2: Triage any remaining failures by first traceback**

If a remaining failure is unrelated to:

- G0 metadata,
- route-readiness coverage, or
- value-flow census implementation/fixture,

stop and write a one-paragraph root-cause note before changing code.

## Task 5: Full Suite Verification

**Files:**
- No code edits

- [ ] **Step 1: Run full suite with cache cleared**

Run in tmux:

```bash
/home/ollie/miniconda3/bin/pytest -n auto --cache-clear tests
```

Monitor:

```bash
tmux -S /tmp/claude-tmux-sockets/claude.sock capture-pane -p -J -t pytest-all:0.0 -S -200
```

Expected: substantially reduced failures. The target is zero failures unless unrelated dirty workspace changes remain.

- [ ] **Step 2: If failures remain, produce grouped triage**

Run:

```bash
/home/ollie/miniconda3/bin/python - <<'PY'
import json
from collections import Counter
from pathlib import Path
path = Path(".pytest_cache/v/cache/lastfailed")
data = json.loads(path.read_text()) if path.exists() else {}
for file, count in Counter(k.split("::", 1)[0] for k in data).most_common():
    print(f"{count:3} {file}")
PY
```

Then serially reproduce one representative per group before fixing.

- [ ] **Step 3: Final status**

Run:

```bash
git status --short
git log --oneline -5
```

Report:

- full-suite result;
- exact commits created;
- remaining dirty files intentionally left untouched;
- any remaining failures with representative traceback and root-cause hypothesis.

