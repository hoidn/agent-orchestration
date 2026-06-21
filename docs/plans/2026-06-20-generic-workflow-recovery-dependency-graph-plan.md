# Generic Workflow Recovery Dependency Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ad hoc prerequisite-recovery routing with a generic dependency-edge model that prevents circular prerequisite churn and routes blocked work by machine-readable readiness semantics.

**Architecture:** Introduce workflow-agnostic dependency-edge utilities that model blocked work, blocker work, downstream work, readiness predicates, and retry targets as structured state. Keep the first integration in the Lisp frontend drain, but make the detector, recorder, selector contract, and tests operate on generic edge semantics instead of bootstrap/summary-specific constants. Legacy bootstrap-boundary fields remain readable only as a compatibility import into the generic model, not as the long-term mechanism.

**Tech Stack:** Python workflow helper scripts under `workflows/library/scripts/`, workflow YAML under `workflows/examples/lisp_frontend_design_delta_drain.yaml`, selector/recovery prompts under `workflows/library/prompts/`, runtime tests in `tests/test_lisp_frontend_autonomous_drain_runtime.py`, and new focused unit tests in `tests/test_workflow_recovery_dependency_graph.py`.

---

## Scope Check

This plan fixes the workflow-control problem exposed by repeated prerequisite-recovery blocks. It does not implement the runtime-native drain authoring target itself and does not modify Workflow Lisp compiler/runtime semantics.

The concrete bootstrap/summary case is only the motivating instance:

- blocked work: `workflow-lisp-runtime-native-drain-runtime-phase-context-bootstrap-for-imported-stdlib-adapters`
- downstream work: `workflow-lisp-runtime-native-drain-work-item-summary-ownership-over-imported-finalize-selected-item`
- old problem: the workflow encoded this as one-off fields and selected downstream work before the upstream route was exercisable

The implemented fix must work for any workflow that can represent blocked work, prerequisites, retry readiness, and downstream dependencies.

## File Structure

Create:

- `workflows/library/scripts/workflow_recovery_dependencies.py`
  - Small pure helper module for dependency-edge normalization, cycle detection, completion lookup, ready/retry routing, and compatibility import from old fields.
- `tests/test_workflow_recovery_dependency_graph.py`
  - Focused workflow-agnostic tests for dependency edges, cycles, completed prerequisites, downstream gating, and stale/missing evidence.

Modify:

- `workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py`
  - Consume generic dependency-edge decisions when deciding `SELECT_PREREQUISITE_WORK`, `RECOVER_BLOCKED_DESIGN_GAP`, or `BLOCKED`.
- `workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py`
  - Record generic dependency edges for `PREREQUISITE_GAP_REQUIRED`; retain bootstrap-specific fields only as compatibility input.
- `workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py`
  - Update the graph edge after selected prerequisite completion/block/retry instead of hard-coding self-prerequisite or downstream behavior.
- `workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md`
  - Require prerequisite selections to identify a structured blocker edge rather than prose-only `prerequisite_relation`.
- `workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md`
  - Ask for generic dependency-edge fields when classifying a prerequisite blocker.
- `workflows/examples/lisp_frontend_design_delta_drain.yaml`
  - Extend output bundles for the generic dependency fields while keeping old fields readable during migration.
- `tests/test_lisp_frontend_autonomous_drain_runtime.py`
  - Replace bootstrap-specific assertions with generic dependency graph behavior and retain one compatibility-input test.

Inspect only:

- `docs/work_definition_model.md`
- `docs/workflow_drafting_guide.md`
- `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
- `docs/backlog/active/2026-06-19-prerequisite-recovery-target-design-boundary.md`

Do not modify unless a test or docs contract requires it:

- target design docs
- Workflow Lisp compiler/runtime files
- `.orc` workflow family files

## Data Model

Use one edge shape internally:

```json
{
  "schema": "workflow_recovery_dependency_edge/v1",
  "blocked_work": {
    "source": "DESIGN_GAP",
    "id": "blocked-work-id"
  },
  "blocker_work": {
    "source": "DESIGN_GAP",
    "id": "blocker-work-id"
  },
  "relation": "requires_completion",
  "reason_code": "missing_runtime_capability",
  "ready_when": {
    "kind": "completed",
    "source": "DESIGN_GAP",
    "id": "blocker-work-id"
  },
  "retry_target": {
    "source": "DESIGN_GAP",
    "id": "blocked-work-id"
  },
  "downstream_work": [
    {
      "source": "DESIGN_GAP",
      "id": "downstream-work-id"
    }
  ],
  "status": "waiting",
  "evidence": {
    "failure_code": "machine-readable-code",
    "selection_bundle_path": "",
    "created_by": "blocked_recovery_classifier"
  }
}
```

Allowed `relation` values for this slice:

- `requires_completion`
- `requires_retry`
- `blocked_until_ready`

Allowed `status` values for this slice:

- `waiting`
- `ready_to_retry`
- `blocked`
- `invalid_cycle`
- `missing_evidence`
- `completed`

Rules:

- `blocked_work` and `blocker_work` must differ for `requires_completion`.
- A self edge is allowed only for `requires_retry`, and then `ready_when` must name existing completion or retry evidence.
- The graph must reject a blocker that depends, directly or indirectly, on the blocked work.
- If `ready_when` is satisfied, route to retry the `retry_target`; do not draft a new prerequisite.
- If `downstream_work` exists, it is not selectable until the blocker edge is satisfied or removed.
- Prose `prerequisite_relation` may explain the edge but is never authority.

## Task 1: Add Pure Dependency-Graph Unit Tests

**Files:**

- Create: `tests/test_workflow_recovery_dependency_graph.py`
- Create: `workflows/library/scripts/workflow_recovery_dependencies.py`

- [ ] **Step 1: Write failing tests for edge normalization**

Add tests:

```python
from workflows.library.scripts.workflow_recovery_dependencies import normalize_edge


def test_normalize_dependency_edge_requires_distinct_completion_blocker():
    edge = normalize_edge({
        "blocked_work": {"source": "DESIGN_GAP", "id": "parser"},
        "blocker_work": {"source": "DESIGN_GAP", "id": "parser"},
        "relation": "requires_completion",
        "reason_code": "missing_parser",
        "ready_when": {"kind": "completed", "source": "DESIGN_GAP", "id": "parser"},
        "retry_target": {"source": "DESIGN_GAP", "id": "parser"},
    })
    assert edge.status == "invalid_cycle"
    assert edge.reason == "self_completion_dependency"
```

Also add tests for:

- valid `requires_completion`;
- valid self `requires_retry`;
- missing `blocked_work`;
- missing `blocker_work`;
- unsupported relation.

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python -m pytest tests/test_workflow_recovery_dependency_graph.py -q
```

Expected: fail because `workflow_recovery_dependencies.py` does not exist or functions are missing.

- [ ] **Step 3: Implement minimal data model**

In `workflows/library/scripts/workflow_recovery_dependencies.py`, define:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


VALID_SOURCES = {"DESIGN_GAP", "BACKLOG_ITEM"}
VALID_RELATIONS = {"requires_completion", "requires_retry", "blocked_until_ready"}
VALID_STATUSES = {"waiting", "ready_to_retry", "blocked", "invalid_cycle", "missing_evidence", "completed"}


@dataclass(frozen=True)
class WorkRef:
    source: str
    id: str


@dataclass(frozen=True)
class RecoveryDependencyEdge:
    blocked_work: WorkRef | None
    blocker_work: WorkRef | None
    relation: str
    reason_code: str
    ready_when: dict[str, str]
    retry_target: WorkRef | None
    downstream_work: tuple[WorkRef, ...] = ()
    status: str = "waiting"
    reason: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


def normalize_edge(raw: Mapping[str, Any]) -> RecoveryDependencyEdge:
    ...


def edge_to_json(edge: RecoveryDependencyEdge) -> dict[str, Any]:
    ...
```

Keep implementation pure and deterministic. Do not import repo-specific constants.

- [ ] **Step 4: Run unit tests**

Run:

```bash
python -m pytest tests/test_workflow_recovery_dependency_graph.py -q
```

Expected: all dependency graph unit tests pass.

- [ ] **Step 5: Commit**

```bash
git add workflows/library/scripts/workflow_recovery_dependencies.py tests/test_workflow_recovery_dependency_graph.py
git commit -m "Add generic workflow recovery dependency graph"
```

## Task 2: Add Routing Semantics For Completion, Retry, And Cycles

**Files:**

- Modify: `workflows/library/scripts/workflow_recovery_dependencies.py`
- Modify: `tests/test_workflow_recovery_dependency_graph.py`

- [ ] **Step 1: Write failing routing tests**

Add tests for:

- completed blocker routes `ready_to_retry`;
- incomplete blocker routes `waiting`;
- blocked blocker with recoverable metadata routes `blocked`;
- blocker that depends on original blocked work routes `invalid_cycle`;
- downstream work remains not selectable while upstream blocker is waiting;
- stale completed evidence for wrong source does not satisfy edge.

Test API:

```python
from workflows.library.scripts.workflow_recovery_dependencies import evaluate_edge


def test_completed_blocker_routes_retry_target():
    state = {
        "completed_design_gaps": ["bootstrap"],
        "completed_items": [],
        "blocked_design_gaps": {},
        "blocked_items": {},
    }
    edge = normalize_edge({
        "blocked_work": {"source": "DESIGN_GAP", "id": "summary"},
        "blocker_work": {"source": "DESIGN_GAP", "id": "bootstrap"},
        "relation": "requires_completion",
        "ready_when": {"kind": "completed", "source": "DESIGN_GAP", "id": "bootstrap"},
        "retry_target": {"source": "DESIGN_GAP", "id": "summary"},
        "reason_code": "missing_runtime_capability"
    })
    decision = evaluate_edge(edge, state)
    assert decision.route == "RETRY_TARGET"
    assert decision.target.id == "summary"
```

- [ ] **Step 2: Run and verify failure**

Run:

```bash
python -m pytest tests/test_workflow_recovery_dependency_graph.py -q
```

Expected: fail because `evaluate_edge` is missing.

- [ ] **Step 3: Implement evaluation**

Add:

```python
@dataclass(frozen=True)
class RecoveryDependencyDecision:
    route: str
    target: WorkRef | None
    edge: RecoveryDependencyEdge
    reason: str


def evaluate_edge(edge: RecoveryDependencyEdge, run_state: Mapping[str, Any]) -> RecoveryDependencyDecision:
    ...
```

Allowed routes:

- `SELECT_BLOCKER`
- `RETRY_TARGET`
- `BLOCKED_RECOVERABLE`
- `BLOCKED_TERMINAL`
- `INVALID_EDGE`

- [ ] **Step 4: Run focused tests**

Run:

```bash
python -m pytest tests/test_workflow_recovery_dependency_graph.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add workflows/library/scripts/workflow_recovery_dependencies.py tests/test_workflow_recovery_dependency_graph.py
git commit -m "Evaluate workflow recovery dependency edges"
```

## Task 3: Import Legacy Bootstrap Fields Into Generic Edges

**Files:**

- Modify: `workflows/library/scripts/workflow_recovery_dependencies.py`
- Modify: `tests/test_workflow_recovery_dependency_graph.py`

- [ ] **Step 1: Add compatibility-input tests**

Add tests that pass an old blocked entry containing:

- `waiting_on_prerequisite_gap_id`
- `waiting_on_prerequisite_source`
- `downstream_blocked_gap_id`
- `blocking_failure_code`
- `retry_condition`

Expected:

- the helper emits a generic edge;
- the edge status is `invalid_cycle` if the old data encodes a self `requires_completion`;
- the edge is `waiting` if old data encodes a real blocker distinct from blocked work.

Use API:

```python
from workflows.library.scripts.workflow_recovery_dependencies import edge_from_blocked_entry
```

- [ ] **Step 2: Run and verify failure**

Run:

```bash
python -m pytest tests/test_workflow_recovery_dependency_graph.py -q
```

Expected: fail because compatibility import is missing.

- [ ] **Step 3: Implement compatibility import**

Add:

```python
def edge_from_blocked_entry(blocked_work: WorkRef, entry: Mapping[str, Any]) -> RecoveryDependencyEdge | None:
    ...
```

Rules:

- Prefer explicit `recovery_dependency_edge` if present.
- Otherwise import old fields into a generic edge.
- Do not silently transform a self `waiting_on_prerequisite_gap_id` into a valid completion prerequisite.
- Put old field names under `edge.evidence["legacy_fields"]` for debugging.

- [ ] **Step 4: Run tests**

Run:

```bash
python -m pytest tests/test_workflow_recovery_dependency_graph.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add workflows/library/scripts/workflow_recovery_dependencies.py tests/test_workflow_recovery_dependency_graph.py
git commit -m "Import legacy prerequisite metadata as dependency edges"
```

## Task 4: Record Generic Edges For Prerequisite Blockers

**Files:**

- Modify: `workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py`
- Modify: `workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md`
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add failing runtime tests**

In `tests/test_lisp_frontend_autonomous_drain_runtime.py`, add tests:

- `test_prerequisite_recovery_records_generic_dependency_edge`
- `test_prerequisite_recovery_rejects_self_completion_edge`
- `test_prerequisite_recovery_keeps_bootstrap_legacy_fields_compat_only`

Expected state shape:

```python
blocked = state["blocked_design_gaps"]["parser-syntax"]
edge = blocked["recovery_dependency_edge"]
assert edge["blocked_work"] == {"source": "DESIGN_GAP", "id": "parser-syntax"}
assert edge["blocker_work"] == {"source": "DESIGN_GAP", "id": "generic-context-capability"}
assert edge["relation"] == "requires_completion"
assert edge["retry_target"] == {"source": "DESIGN_GAP", "id": "parser-syntax"}
```

- [ ] **Step 2: Run and verify failure**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "generic_dependency_edge or self_completion_edge or bootstrap_legacy_fields_compat_only" -q
```

Expected: fail because no generic edge is recorded.

- [ ] **Step 3: Extend output bundle contract**

In `workflows/examples/lisp_frontend_design_delta_drain.yaml`, add output fields for:

- `recovery_dependency_edge`
- `blocked_work_id`
- `blocked_work_source`
- `blocker_work_id`
- `blocker_work_source`
- `dependency_relation`
- `dependency_reason_code`
- `retry_target_id`
- `retry_target_source`

Keep old bootstrap-specific fields for compatibility during this migration.

- [ ] **Step 4: Update classifier prompt**

In `workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md`, replace the bootstrap-specific instruction block with a generic instruction:

```text
When `blocked_recovery_route` is `PREREQUISITE_GAP_REQUIRED`, include a
`recovery_dependency_edge` object. It must identify blocked work, blocker work,
relation, reason_code, ready_when, retry_target, and optional downstream_work.
Do not encode a self dependency with `relation: requires_completion`; use
`requires_retry` only when the blocked work itself has completion/retry evidence.
If no acyclic blocker can be identified, use `TERMINAL_BLOCKED` with
`reason: prerequisite_dependency_cycle_or_missing_evidence`.
```

- [ ] **Step 5: Update recorder**

In `record_lisp_frontend_blocked_recovery_outcome.py`:

- parse `recovery_dependency_edge` from the recovery bundle;
- normalize it with `normalize_edge`;
- reject invalid edges with a clear `SystemExit`;
- write the normalized edge into the blocked entry as `recovery_dependency_edge`;
- preserve legacy fields only if they arrived in the bundle and do not conflict with the generic edge.

- [ ] **Step 6: Run focused tests**

Run:

```bash
python -m pytest tests/test_workflow_recovery_dependency_graph.py -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "generic_dependency_edge or self_completion_edge or bootstrap_legacy_fields_compat_only" -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add \
  workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py \
  workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md \
  workflows/examples/lisp_frontend_design_delta_drain.yaml \
  tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "Record generic prerequisite recovery dependency edges"
```

## Task 5: Route Recovery Through Generic Edge Decisions

**Files:**

- Modify: `workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py`
- Modify: `workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py`
- Modify: `workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add failing detector tests**

Add tests:

- `test_dependency_edge_detector_selects_blocker`
- `test_dependency_edge_detector_retries_original_after_blocker_complete`
- `test_dependency_edge_detector_blocks_cycle`
- `test_dependency_edge_detector_does_not_select_downstream_while_blocker_waits`

Assertions:

```python
payload = json.loads(detector_output.read_text())
assert payload["pre_selection_route"] == "SELECT_PREREQUISITE_WORK"
assert payload["design_gap_id"] == "parser-syntax"
assert payload["dependency_decision_route"] == "SELECT_BLOCKER"
assert payload["selected_blocker_id"] == "generic-context-capability"
```

- [ ] **Step 2: Run and verify failure**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "dependency_edge_detector" -q
```

Expected: fail because detector ignores generic edges.

- [ ] **Step 3: Update detector**

In `detect_lisp_frontend_blocked_design_gap_recovery.py`:

- remove hard-coded bootstrap boundary validation from the main path;
- import `edge_from_blocked_entry` and `evaluate_edge`;
- when a `PREREQUISITE_GAP_REQUIRED` blocked entry has an edge:
  - `SELECT_BLOCKER` -> emit `SELECT_PREREQUISITE_WORK` with selected blocker metadata;
  - `RETRY_TARGET` -> emit `RECOVER_BLOCKED_DESIGN_GAP` for retry target;
  - `INVALID_EDGE` -> emit `BLOCKED` with reason `prerequisite_dependency_cycle_or_missing_evidence`;
  - `BLOCKED_RECOVERABLE` -> keep original blocked work pending and explain blocker status.
- if only legacy fields exist, import them through `edge_from_blocked_entry`.

- [ ] **Step 4: Update prerequisite recorder**

In `record_lisp_frontend_prerequisite_recovery_outcome.py`:

- use the edge decision to update the original blocked entry;
- mark edge `completed` only when the blocker completion evidence matches `ready_when`;
- set original `recovery_status` to `RETRY_READY` only for `RETRY_TARGET`;
- do not interpret downstream work as the selected prerequisite while the blocker is waiting.

- [ ] **Step 5: Update selector prompt**

In `select_next_design_delta_work.md`, replace prose-only prerequisite guidance with:

```text
If pre-selection metadata provides a dependency edge, select the blocker work
named by that edge. Do not select downstream work while the edge is `waiting`.
If the edge is invalid, cyclic, or lacks evidence, return `BLOCKED` rather than
drafting another prerequisite. Include the edge id/blocked/blocker fields in
the output bundle when selecting prerequisite recovery work.
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
python -m pytest tests/test_workflow_recovery_dependency_graph.py -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "dependency_edge_detector or prerequisite_boundary or prerequisite_recovery" -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add \
  workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py \
  workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py \
  workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md \
  tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "Route prerequisite recovery through dependency edges"
```

## Task 6: Remove Bootstrap-Specific Routing As Authority

**Files:**

- Modify: `workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py`
- Modify: `workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py`
- Modify: `workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add regression for no hard-coded bootstrap route**

Add a test that uses arbitrary ids:

- blocked work: `alpha-feature`
- blocker: `beta-capability`
- downstream: `gamma-cleanup`

Expected behavior must match the bootstrap case without referencing bootstrap constants.

- [ ] **Step 2: Run test and verify it fails before cleanup**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "arbitrary_dependency_edge" -q
```

Expected: fail if code still depends on bootstrap constants.

- [ ] **Step 3: Delete authority constants from routing path**

Remove or quarantine these constants so they are used only in compatibility tests, not detector/recorder logic:

- `BOOTSTRAP_GAP_ID`
- `SUMMARY_OWNERSHIP_GAP_ID`
- `BOOTSTRAP_FAILURE_CODE`
- `BOOTSTRAP_WAIT_STATUS`
- `BOOTSTRAP_WAIT_REASON`
- `BOOTSTRAP_RETRY_CONDITION`
- `BOOTSTRAP_BOUNDARY_DIAGNOSTIC`

If compatibility still needs them, place them inside test fixtures or a local `legacy_bootstrap_boundary_fixture()` helper rather than production routing.

- [ ] **Step 4: Run focused tests**

Run:

```bash
python -m pytest tests/test_workflow_recovery_dependency_graph.py -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "arbitrary_dependency_edge or dependency_edge_detector or prerequisite_boundary or prerequisite_recovery" -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add \
  workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py \
  workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py \
  workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py \
  tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "Remove hardcoded bootstrap prerequisite routing"
```

## Task 7: Integrate With Non-Progress Step-Back

**Files:**

- Modify: `workflows/library/scripts/project_lisp_frontend_progress_signals.py`
- Modify: `workflows/library/scripts/evaluate_workflow_non_progress.py`
- Modify: `tests/test_workflow_non_progress_recovery.py`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add tests for dependency-graph churn signals**

Add cases:

- same invalid edge appears twice -> `STEP_BACK_REQUIRED`;
- prerequisite chain grows beyond threshold -> `STEP_BACK_REQUIRED`;
- edge route transitions from waiting to retry-ready -> counts as accepted progress;
- edge route selects arbitrary downstream work before blocker is ready -> non-progress warning.

- [ ] **Step 2: Run and verify failure**

Run:

```bash
python -m pytest tests/test_workflow_non_progress_recovery.py -q
```

Expected: fail for new dependency-edge signal expectations.

- [ ] **Step 3: Project dependency events**

In `project_lisp_frontend_progress_signals.py`, include generic events:

- `dependency_edge_recorded`
- `dependency_edge_waiting`
- `dependency_edge_retry_ready`
- `dependency_edge_invalid`
- `dependency_chain_growth`

Do not special-case bootstrap/summary names.

- [ ] **Step 4: Evaluate dependency events**

In `evaluate_workflow_non_progress.py`:

- treat `dependency_edge_retry_ready` as accepted progress;
- treat repeated `dependency_edge_invalid` with same fingerprint as non-progress;
- treat growing unresolved dependency chain as non-progress;
- keep existing repeated-block/no-change thresholds.

- [ ] **Step 5: Run tests**

Run:

```bash
python -m pytest tests/test_workflow_non_progress_recovery.py tests/test_lisp_frontend_autonomous_drain_runtime.py -k "progress_signals or non_progress or dependency_edge" -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add \
  workflows/library/scripts/project_lisp_frontend_progress_signals.py \
  workflows/library/scripts/evaluate_workflow_non_progress.py \
  tests/test_workflow_non_progress_recovery.py \
  tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "Include dependency edges in workflow non-progress detection"
```

## Task 8: Verify Workflow Shape And Smoke Recovery

**Files:**

- Modify only if tests expose a real contract mismatch:
  - `workflows/examples/lisp_frontend_design_delta_drain.yaml`
  - `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Collect affected tests**

Run:

```bash
python -m pytest --collect-only \
  tests/test_workflow_recovery_dependency_graph.py \
  tests/test_workflow_non_progress_recovery.py \
  tests/test_lisp_frontend_autonomous_drain_runtime.py -q
```

Expected: collection succeeds; update selectors if any new test names changed.

- [ ] **Step 2: Run focused tests**

Run:

```bash
python -m pytest tests/test_workflow_recovery_dependency_graph.py -q
python -m pytest tests/test_workflow_non_progress_recovery.py -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "dependency_edge or prerequisite_recovery or workflow_shape or design_gap_runtime_smoke" -q
```

Expected: pass.

- [ ] **Step 3: Dry-run the drain workflow**

Use the same input shape as current runtime-native drain launches:

```bash
python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml \
  --dry-run \
  --input steering_path=docs/steering.md \
  --input target_design_path=docs/design/workflow_lisp_runtime_native_drain_authoring.md \
  --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md \
  --input post_wcc_inventory_path=docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/post_wcc_current_state_inventory.json \
  --input command_adapter_contract_path=docs/design/workflow_command_adapter_contract.md \
  --input backlog_root=docs/backlog/active \
  --input progress_ledger_path=state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/progress_ledger.json \
  --input drain_state_root=state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain \
  --input run_state_target_path=state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain/run_state.json \
  --input drain_summary_target_path=artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain-summary.json \
  --input artifact_work_root=artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN \
  --input artifact_checks_root=artifacts/checks/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN \
  --input artifact_review_root=artifacts/review/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN \
  --input architecture_index_root=docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps \
  --input design_gap_draft_provider=codex \
  --input design_gap_draft_model=gpt-5.5 \
  --input design_gap_draft_effort=high \
  --input implementation_execute_provider=codex \
  --input implementation_review_provider=codex \
  --input done_review_provider=codex
```

Expected: workflow validation succeeds; advisory lints are acceptable only if pre-existing and unrelated.

- [ ] **Step 4: Whitespace check**

Run:

```bash
git diff --check
```

Expected: pass.

- [ ] **Step 5: Commit any final workflow-shape corrections**

```bash
git add workflows/examples/lisp_frontend_design_delta_drain.yaml tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "Verify dependency-edge prerequisite recovery workflow shape"
```

Skip this commit if there are no changes after verification.

## Task 9: Document The General Pattern

**Files:**

- Modify: `docs/workflow_drafting_guide.md`
- Modify only if discoverability requires it: `workflows/README.md`

- [ ] **Step 1: Add concise authoring guidance**

In `docs/workflow_drafting_guide.md`, add a short section:

```markdown
### Recovery Dependency Edges

When a workflow can block on prerequisite work, record a machine-readable
dependency edge instead of prose-only prerequisite text. The edge should name
blocked work, blocker work, readiness evidence, retry target, and downstream
work. Recovery selectors must reject cycles, retry the original work once the
blocker is ready, and route to step-back rather than drafting another local
prerequisite when no acyclic blocker exists.
```

- [ ] **Step 2: Run doc grep**

Run:

```bash
rg -n "Recovery Dependency Edges|recovery_dependency_edge" docs/workflow_drafting_guide.md workflows/README.md
```

Expected: new guidance is discoverable.

- [ ] **Step 3: Commit docs**

```bash
git add docs/workflow_drafting_guide.md workflows/README.md
git commit -m "Document workflow recovery dependency edges"
```

## Final Verification

Run:

```bash
python -m pytest tests/test_workflow_recovery_dependency_graph.py -q
python -m pytest tests/test_workflow_non_progress_recovery.py -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "dependency_edge or prerequisite_recovery or workflow_shape or design_gap_runtime_smoke or progress_signals" -q
python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml --dry-run \
  --input steering_path=docs/steering.md \
  --input target_design_path=docs/design/workflow_lisp_runtime_native_drain_authoring.md \
  --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md \
  --input post_wcc_inventory_path=docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/post_wcc_current_state_inventory.json \
  --input command_adapter_contract_path=docs/design/workflow_command_adapter_contract.md \
  --input backlog_root=docs/backlog/active \
  --input progress_ledger_path=state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/progress_ledger.json \
  --input drain_state_root=state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain \
  --input run_state_target_path=state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain/run_state.json \
  --input drain_summary_target_path=artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain-summary.json \
  --input artifact_work_root=artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN \
  --input artifact_checks_root=artifacts/checks/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN \
  --input artifact_review_root=artifacts/review/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN \
  --input architecture_index_root=docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps \
  --input design_gap_draft_provider=codex \
  --input design_gap_draft_model=gpt-5.5 \
  --input design_gap_draft_effort=high \
  --input implementation_execute_provider=codex \
  --input implementation_review_provider=codex \
  --input done_review_provider=codex
git diff --check
```

Expected:

- generic dependency graph tests pass;
- existing prerequisite recovery behavior still works through generic edges;
- arbitrary non-bootstrap dependency edges work;
- self-completion and dependency cycles fail closed;
- downstream work is not selected before blocker readiness;
- completed blocker evidence routes to retry target;
- non-progress detector recognizes repeated invalid dependency edges; and
- workflow dry-run succeeds.

## Resume Policy For Active Runs

Because this changes workflow YAML and scripts used by active runs, do not silently continue a running workflow on old checksums.

After implementation:

1. Prefer finishing or suspending the current run at a stable boundary.
2. If preserving prior approved stages is required, back up `.orchestrate/runs/<run_id>/state.json`, update only the recorded workflow checksum to the current workflow file checksum, and resume.
3. Otherwise use `orchestrator resume <run_id> --force-restart` or start a fresh run with a clean namespace.

Record which choice was used in the final implementation report.
