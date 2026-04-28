# Approved-Design Redesign Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make approved-design continuation workflows handle plan-level `ESCALATE_REDESIGN` as a normal controlled route instead of crashing when `current_phase` becomes `big_design`.

**Architecture:** Use one phase-complete tranche stack as the source of truth for `big_design -> plan -> implementation` routing, with a configurable initial phase. Keep `major_project_tranche_plan_impl_from_approved_design_stack.yaml` as a compatibility adapter that starts the complete stack at `plan`, so future redesign and roadmap-escalation behavior cannot drift from the full drain stack.

**Tech Stack:** Agent-orchestration DSL v2.12, YAML call workflows, Python route helpers, pytest workflow contract tests, orchestrator smoke checks.

---

## Context

The crash is a workflow contract bug, not an EasySpin numerics bug. The plan phase can validly return `ESCALATE_REDESIGN`; `workflows/library/scripts/major_project_tranche_phase_routes.py route-after-plan` responds by writing `big_design` into `${item_state_root}/current_phase.txt`. The approved-design continuation stack then fails because `ReadCurrentPhase` only allows `["plan", "implementation"]` and `RouteCurrentPhase` has no `big_design` case.

The principled invariant is:

> Any workflow that permits a route helper to write `current_phase=X` must either route `X` in the same loop or convert the decision into a typed terminal outcome handled by its caller.

Do not fix this by weakening plan review, suppressing `ESCALATE_REDESIGN`, or treating a valid redesign escalation as a provider failure.

Do not create a worktree. This repo's `AGENTS.md` explicitly forbids worktrees.

## File Structure

- Modify: `workflows/library/major_project_tranche_design_plan_impl_stack.yaml`
  - Add `initial_phase` input with default `big_design`.
  - Initialize `current_phase.txt` idempotently from `initial_phase` only when the file does not already exist.
  - Keep all phase routing in this stack.

- Modify: `workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml`
  - Replace the duplicate plan/implementation loop with an adapter call into `major_project_tranche_design_plan_impl_stack.yaml`.
  - Add pass-through inputs for `big_design_phase_state_root` and `design_review_report_target_path`.
  - Pass `initial_phase: plan`.
  - Export the full stack outcomes, including redesign-side outcomes.

- Modify: `workflows/examples/major_project_tranche_continue_from_approved_design_v2_call.yaml`
  - Pass `big_design_phase_state_root` and `design_review_report_target_path` into the approved-design adapter.
  - Route stack outcomes explicitly before manifest update so `ESCALATE_ROADMAP_REVISION` does not fall into `update_major_project_tranche_manifest.py`, which correctly rejects roadmap revision there.

- Modify: `workflows/README.md`
  - Update the approved-design continuation description to say it starts at plan but can route back through redesign when the plan review escalates.

- Modify: `tests/test_major_project_workflows.py`
  - Add static contract coverage for the configurable initial phase and adapter.
  - Add a runtime mocked-provider regression where approved-design continuation returns `ESCALATE_REDESIGN`, runs big design, then resumes plan/implementation from the new design.
  - Add a runtime regression for redesign-to-roadmap-escalation being reported as a controlled blocked/terminal continuation outcome, not a crash in manifest update.

## Task 1: Lock the Routing Contract With Failing Tests

**Files:**
- Modify: `tests/test_major_project_workflows.py`

- [ ] **Step 1: Add a static test for configurable initial phase**

Add or update a test near `test_tranche_stack_uses_current_phase_visit_roots_for_reentry`:

```python
def test_full_tranche_stack_supports_configurable_initial_phase():
    workflow = _load_yaml("workflows/library/major_project_tranche_design_plan_impl_stack.yaml")

    assert workflow["inputs"]["initial_phase"] == {
        "type": "enum",
        "allowed": ["big_design", "plan", "implementation"],
        "default": "big_design",
    }

    init_step = _step_by_name(workflow, "InitializeItemState")
    command_text = "\n".join(str(part) for part in init_step["command"])
    assert "${inputs.initial_phase}" in command_text
    assert "current_phase.txt" in command_text
    assert "if [ ! -f" in command_text or "if [ ! -s" in command_text
```

- [ ] **Step 2: Update the approved-design stack static test**

Change `test_approved_design_stack_uses_current_phase_visit_roots_for_reentry` so it no longer expects a local `RouteCurrentPhase` with only `plan` and `implementation`. It should assert the stack is an adapter:

```python
def test_approved_design_stack_delegates_to_phase_complete_stack():
    workflow = _load_yaml("workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml")

    assert workflow["imports"]["phase_complete_tranche_stack"] == "major_project_tranche_design_plan_impl_stack.yaml"
    assert "big_design_phase_state_root" in workflow["inputs"]
    assert "design_review_report_target_path" in workflow["inputs"]

    run_step = _step_by_name(workflow, "RunPhaseCompleteStackFromApprovedDesign")
    assert run_step["call"] == "phase_complete_tranche_stack"
    assert run_step["with"]["initial_phase"] == "plan"
    assert run_step["with"]["design_target_path"] == {"ref": "inputs.design_path"}
    assert run_step["with"]["big_design_phase_state_root"] == {"ref": "inputs.big_design_phase_state_root"}
    assert run_step["with"]["design_review_report_target_path"] == {
        "ref": "inputs.design_review_report_target_path"
    }
```

- [ ] **Step 3: Add a wrapper static test for controlled roadmap escalation**

Add a test for `workflows/examples/major_project_tranche_continue_from_approved_design_v2_call.yaml`:

```python
def test_continue_from_approved_design_routes_redesign_roadmap_escalation_before_manifest_update():
    workflow = _load_yaml("workflows/examples/major_project_tranche_continue_from_approved_design_v2_call.yaml")

    run_step = _step_by_name(workflow, "RunSelectedTrancheFromApprovedDesign")
    assert run_step["with"]["big_design_phase_state_root"] == {
        "ref": "root.steps.SelectNextTranche.artifacts.big_design_phase_state_root"
    }
    assert run_step["with"]["design_review_report_target_path"] == {
        "ref": "root.steps.SelectNextTranche.artifacts.design_review_report_target_path"
    }

    route_step = _step_by_name(workflow, "RouteSelectedTrancheOutcome")
    assert set(route_step["match"]["cases"]) == {
        "APPROVED",
        "SKIPPED_AFTER_DESIGN",
        "SKIPPED_AFTER_PLAN",
        "SKIPPED_AFTER_IMPLEMENTATION",
        "ESCALATE_ROADMAP_REVISION",
    }
```

Use the actual route step shape from Task 4; the important assertion is that `ESCALATE_ROADMAP_REVISION` has a dedicated branch and does not go directly to `UpdateTrancheManifest`.

- [ ] **Step 4: Run the new static tests and confirm failure**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration pytest tests/test_major_project_workflows.py -q -k "initial_phase or approved_design_stack or continue_from_approved_design_routes"
```

Expected: FAIL before implementation because `initial_phase` does not exist and the approved-design stack is still a partial local router.

## Task 2: Make the Full Tranche Stack Resume-Safe and Configurable

**Files:**
- Modify: `workflows/library/major_project_tranche_design_plan_impl_stack.yaml`

- [ ] **Step 1: Add `initial_phase` input**

Add this input near the other stack-control inputs:

```yaml
  initial_phase:
    type: enum
    allowed: ["big_design", "plan", "implementation"]
    default: big_design
```

- [ ] **Step 2: Make phase initialization idempotent**

Replace the unconditional write:

```bash
printf '%s\n' big_design > "${inputs.item_state_root}/current_phase.txt"
```

with:

```bash
if [ ! -s "${inputs.item_state_root}/current_phase.txt" ]; then
  printf '%s\n' "${inputs.initial_phase}" > "${inputs.item_state_root}/current_phase.txt"
fi
```

Keep the existing `mkdir`, upstream initialization, phase visit initialization, and default roadmap-change-request pointer behavior.

- [ ] **Step 3: Verify existing callers still default to big design**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration pytest tests/test_major_project_workflows.py -q -k "tranche_stack_uses_current_phase_visit_roots_for_reentry or full_tranche_stack_supports_configurable_initial_phase"
```

Expected: PASS after the YAML change.

## Task 3: Convert the Approved-Design Stack Into an Adapter

**Files:**
- Modify: `workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml`

- [ ] **Step 1: Replace local phase imports**

Change imports from:

```yaml
imports:
  plan_phase: major_project_tranche_plan_phase.yaml
  implementation_phase: major_project_tranche_implementation_phase.yaml
```

to:

```yaml
imports:
  phase_complete_tranche_stack: major_project_tranche_design_plan_impl_stack.yaml
```

- [ ] **Step 2: Add missing pass-through inputs**

Add:

```yaml
  big_design_phase_state_root: {type: relpath, under: state}
  design_review_report_target_path: {type: relpath, under: artifacts/review}
```

Keep the existing `design_path` input name for compatibility; it is the approved design file and will be passed to the full stack as `design_target_path`.

- [ ] **Step 3: Widen adapter outputs to match the phase-complete stack**

Set `item_outcome.allowed` to:

```yaml
allowed: ["APPROVED", "SKIPPED_AFTER_DESIGN", "SKIPPED_AFTER_PLAN", "SKIPPED_AFTER_IMPLEMENTATION", "ESCALATE_ROADMAP_REVISION"]
```

Add:

```yaml
  roadmap_change_request_path:
    type: relpath
    under: state
    must_exist_target: true
    from: {ref: root.steps.PublishItemOutputs.artifacts.roadmap_change_request_path}
```

- [ ] **Step 4: Replace the local loop with one call**

After `InitializeItemState`, call the complete stack:

```yaml
  - name: RunPhaseCompleteStackFromApprovedDesign
    id: run_phase_complete_stack_from_approved_design
    call: phase_complete_tranche_stack
    with:
      initial_phase: plan
      item_state_root: {ref: inputs.item_state_root}
      upstream_escalation_context_path: {ref: inputs.upstream_escalation_context_path}
      big_design_phase_state_root: {ref: inputs.big_design_phase_state_root}
      plan_phase_state_root: {ref: inputs.plan_phase_state_root}
      implementation_phase_state_root: {ref: inputs.implementation_phase_state_root}
      project_brief_path: {ref: inputs.project_brief_path}
      project_roadmap_path: {ref: inputs.project_roadmap_path}
      tranche_manifest_path: {ref: inputs.tranche_manifest_path}
      tranche_brief_path: {ref: inputs.tranche_brief_path}
      design_target_path: {ref: inputs.design_path}
      design_review_report_target_path: {ref: inputs.design_review_report_target_path}
      plan_target_path: {ref: inputs.plan_target_path}
      plan_review_report_target_path: {ref: inputs.plan_review_report_target_path}
      execution_report_target_path: {ref: inputs.execution_report_target_path}
      implementation_review_report_target_path: {ref: inputs.implementation_review_report_target_path}
      item_summary_target_path: {ref: inputs.item_summary_target_path}
```

Then publish outputs from that call instead of local final pointer files:

```yaml
  - name: PublishItemOutputs
    id: publish_item_outputs
    command: ["bash", "-lc", "true"]
    expected_outputs:
      - name: item_outcome
        path: ${inputs.item_state_root}/item_outcome.txt
        type: enum
        allowed: ["APPROVED", "SKIPPED_AFTER_DESIGN", "SKIPPED_AFTER_PLAN", "SKIPPED_AFTER_IMPLEMENTATION", "ESCALATE_ROADMAP_REVISION"]
      - name: execution_report_path
        path: ${inputs.item_state_root}/final_execution_report_path.txt
        type: relpath
        under: artifacts/work
        must_exist_target: true
      - name: item_summary_path
        path: ${inputs.item_state_root}/final_item_summary_path.txt
        type: relpath
        under: artifacts/work
        must_exist_target: true
      - name: roadmap_change_request_path
        path: ${inputs.item_state_root}/final_roadmap_change_request_path.txt
        type: relpath
        under: state
        must_exist_target: true
```

- [ ] **Step 5: Run focused static tests**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration pytest tests/test_major_project_workflows.py -q -k "approved_design_stack_delegates_to_phase_complete_stack or full_tranche_stack_supports_configurable_initial_phase"
```

Expected: PASS.

## Task 4: Route Approved-Design Wrapper Outcomes Explicitly

**Files:**
- Modify: `workflows/examples/major_project_tranche_continue_from_approved_design_v2_call.yaml`

- [ ] **Step 1: Pass redesign inputs into the adapter**

Add these `with` entries to `RunSelectedTrancheFromApprovedDesign`:

```yaml
      big_design_phase_state_root:
        ref: root.steps.SelectNextTranche.artifacts.big_design_phase_state_root
      design_review_report_target_path:
        ref: root.steps.SelectNextTranche.artifacts.design_review_report_target_path
```

- [ ] **Step 2: Add an outcome routing step before manifest update**

Insert a `RouteSelectedTrancheOutcome` match step after `RunSelectedTrancheFromApprovedDesign`. The intent is:

```yaml
  - name: RouteSelectedTrancheOutcome
    id: route_selected_tranche_outcome
    match:
      ref: root.steps.RunSelectedTrancheFromApprovedDesign.artifacts.item_outcome
      cases:
        APPROVED:
          id: approved_or_completed
          steps:
            - name: UpdateTrancheManifest
              id: update_tranche_manifest
              ...
        SKIPPED_AFTER_DESIGN:
          id: skipped_after_design
          steps:
            - name: UpdateTrancheManifest
              id: update_tranche_manifest
              ...
        SKIPPED_AFTER_PLAN:
          id: skipped_after_plan
          steps:
            - name: UpdateTrancheManifest
              id: update_tranche_manifest
              ...
        SKIPPED_AFTER_IMPLEMENTATION:
          id: skipped_after_implementation
          steps:
            - name: UpdateTrancheManifest
              id: update_tranche_manifest
              ...
        ESCALATE_ROADMAP_REVISION:
          id: roadmap_revision_required
          steps:
            - name: PublishRoadmapRevisionBlockedOutcome
              id: publish_roadmap_revision_blocked_outcome
              command:
                - python
                - workflows/library/scripts/publish_major_project_continue_outcome.py
                - --selection-bundle
                - ${inputs.drain_state_root}/selected-tranche.json
                - --item-outcome
                - ESCALATE_ROADMAP_REVISION
                - --output-bundle
                - ${inputs.drain_state_root}/manifest-update.json
```

If there is no existing helper for the `ESCALATE_ROADMAP_REVISION` branch, create one in Task 5. Do not call `update_major_project_tranche_manifest.py` for `ESCALATE_ROADMAP_REVISION`; that script is intentionally scoped to manifest update after approved/skipped tranche completion.

- [ ] **Step 3: Update wrapper outputs to read from the route step**

Change root outputs so `drain_status`, `tranche_manifest_path`, `execution_report_path`, and `item_summary_path` come from the route step's artifacts, not a top-level `UpdateTrancheManifest` step. Keep `drain_status.allowed` as `["CONTINUE", "BLOCKED"]`.

- [ ] **Step 4: Update wrapper output bundle enums**

Where the wrapper exposes `item_outcome`, allow:

```yaml
["APPROVED", "SKIPPED_AFTER_DESIGN", "SKIPPED_AFTER_PLAN", "SKIPPED_AFTER_IMPLEMENTATION", "ESCALATE_ROADMAP_REVISION"]
```

- [ ] **Step 5: Run focused static tests**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration pytest tests/test_major_project_workflows.py -q -k "continue_from_approved_design_routes_redesign_roadmap_escalation_before_manifest_update"
```

Expected: PASS.

## Task 5: Add a Tiny Continue-Outcome Publisher if Needed

**Files:**
- Create if needed: `workflows/library/scripts/publish_major_project_continue_outcome.py`
- Modify: `tests/test_major_project_workflows.py`

- [ ] **Step 1: Write tests for the helper**

If Task 4 needs a helper, add direct unit coverage in `tests/test_major_project_workflows.py` or a focused script test module:

```python
def test_publish_continue_outcome_blocks_on_roadmap_revision(tmp_path: Path):
    selection_bundle = tmp_path / "state/demo/selected-tranche.json"
    selection_bundle.parent.mkdir(parents=True)
    selection_bundle.write_text(
        json.dumps(
            {
                "tranche_manifest_path": "state/demo/tranche_manifest.json",
                "item_state_root": "state/demo/items/project/tranche",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    item_root = tmp_path / "state/demo/items/project/tranche"
    item_root.mkdir(parents=True)
    (item_root / "item_outcome.txt").write_text("ESCALATE_ROADMAP_REVISION\n", encoding="utf-8")
    (item_root / "final_execution_report_path.txt").write_text("artifacts/work/report.md\n", encoding="utf-8")
    (item_root / "final_item_summary_path.txt").write_text("artifacts/work/summary.json\n", encoding="utf-8")
    (item_root / "final_roadmap_change_request_path.txt").write_text("state/demo/roadmap-change.json\n", encoding="utf-8")
    (tmp_path / "artifacts/work").mkdir(parents=True)
    (tmp_path / "artifacts/work/report.md").write_text("report\n", encoding="utf-8")
    (tmp_path / "artifacts/work/summary.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "state/demo/roadmap-change.json").write_text("{}\n", encoding="utf-8")

    payload = publish_continue_outcome(
        root=tmp_path,
        selection_bundle_path="state/demo/selected-tranche.json",
        item_outcome="ESCALATE_ROADMAP_REVISION",
        output_bundle_path="state/demo/manifest-update.json",
    )

    assert payload["drain_status"] == "BLOCKED"
    assert payload["item_outcome"] == "ESCALATE_ROADMAP_REVISION"
    assert payload["roadmap_change_request_path"] == "state/demo/roadmap-change.json"
```

- [ ] **Step 2: Implement the helper**

Keep it generic and small:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def publish_continue_outcome(
    *,
    root: Path,
    selection_bundle_path: str,
    item_outcome: str,
    output_bundle_path: str,
) -> dict[str, Any]:
    root = root.resolve()
    selection = json.loads((root / selection_bundle_path).read_text(encoding="utf-8"))
    item_root = root / selection["item_state_root"]
    execution_report_path = (item_root / "final_execution_report_path.txt").read_text(encoding="utf-8").strip()
    item_summary_path = (item_root / "final_item_summary_path.txt").read_text(encoding="utf-8").strip()
    payload: dict[str, Any] = {
        "drain_status": "BLOCKED",
        "item_outcome": item_outcome,
        "tranche_manifest_path": selection["tranche_manifest_path"],
        "execution_report_path": execution_report_path,
        "item_summary_path": item_summary_path,
    }
    roadmap_pointer = item_root / "final_roadmap_change_request_path.txt"
    if roadmap_pointer.exists():
        payload["roadmap_change_request_path"] = roadmap_pointer.read_text(encoding="utf-8").strip()
    output_path = root / output_bundle_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection-bundle", required=True)
    parser.add_argument("--item-outcome", required=True)
    parser.add_argument("--output-bundle", required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    publish_continue_outcome(
        root=args.root,
        selection_bundle_path=args.selection_bundle,
        item_outcome=args.item_outcome,
        output_bundle_path=args.output_bundle,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Harden path validation if this helper expands beyond internal workflow use. Keep the first implementation narrow unless tests require more.

- [ ] **Step 3: Run helper tests**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration pytest tests/test_major_project_workflows.py -q -k "publish_continue_outcome"
```

Expected: PASS.

## Task 6: Add Runtime Regression for Redesign Re-Entry

**Files:**
- Modify: `tests/test_major_project_workflows.py`

- [ ] **Step 1: Add mocked-provider runtime test**

Create a test modeled on `test_continue_from_approved_design_runtime_with_mocked_providers`. The provider sequence should be:

```python
provider_sequence = [
    "DraftPlan",
    "ReviewPlanTracked",
    "DraftBigDesign",
    "ReviewBigDesign",
    "DraftPlan",
    "ReviewPlanTracked",
    "ExecuteImplementation",
    "ReviewImplementation",
]
```

The first `ReviewPlanTracked` writes `ESCALATE_REDESIGN` and `final_plan_escalation_context_path.txt`. The big-design review writes `APPROVE`. The second plan and implementation reviews write `APPROVE`.

Assert:

```python
assert state["status"] == "completed"
assert state["steps"]["RunSelectedTrancheFromApprovedDesign"]["artifacts"]["item_outcome"] == "APPROVED"
assert (tmp_path / f"{item_root}/current_phase.txt").read_text(encoding="utf-8").strip() == "implementation"
assert (tmp_path / f"{item_root}/current_big_design_phase_state_root.txt").exists()
```

Also assert that the approved-design file path is the design target consumed after redesign:

```python
assert design_path.read_text(encoding="utf-8").startswith("# Redesigned")
```

- [ ] **Step 2: Run the regression and confirm it fails before implementation**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration pytest tests/test_major_project_workflows.py -q -k "continue_from_approved_design and redesign"
```

Expected before implementation: FAIL with an invalid `big_design` current phase or missing adapter inputs. Expected after Tasks 2-5: PASS.

## Task 7: Update Documentation

**Files:**
- Modify: `workflows/README.md`

- [ ] **Step 1: Update the approved-design continuation row**

Replace the old description for `workflows/examples/major_project_tranche_continue_from_approved_design_v2_call.yaml` with:

```markdown
One-tranche major-project continuation driver: selects the next ready tranche from an existing manifest, starts from an already-approved design at the plan phase, and still routes plan-level redesign escalation through the full big-design/plan/implementation stack before updating or blocking the manifest.
```

- [ ] **Step 2: Update the approved-design library row**

Replace the old description for `workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml` with:

```markdown
Compatibility adapter for approved-design continuation: invokes the phase-complete major-project tranche stack with `initial_phase: plan`, preserving the historical input shape while sharing redesign, replan, implementation, and roadmap-escalation routing with the full stack.
```

## Task 8: Verify Workflow Loading and Runtime Behavior

**Files:**
- No source files unless checks reveal issues.

- [ ] **Step 1: Run focused tests**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration pytest tests/test_major_project_workflows.py -q -k "initial_phase or approved_design_stack or continue_from_approved_design"
```

Expected: PASS.

- [ ] **Step 2: Run collect-only if tests were added or renamed**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration pytest tests/test_major_project_workflows.py --collect-only -q
```

Expected: collection succeeds.

- [ ] **Step 3: Run an orchestrator smoke check**

Run the narrowest available dry-run/fixture command used by existing major-project workflow tests. If no direct dry-run fixture exists, run the mocked-provider runtime test from Task 6 as the smoke check and record that decision in the final note.

Expected: the approved-design continuation wrapper no longer crashes when a plan review escalates to redesign.

- [ ] **Step 4: Run diff hygiene**

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

## Task 9: Downstream Sync and Recovery Runbook

**Files:**
- Optional sync target: `/home/ollie/Documents/EasySpin/workflows/library/major_project_tranche_design_plan_impl_stack.yaml`
- Optional sync target: `/home/ollie/Documents/EasySpin/workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml`
- Optional sync target: `/home/ollie/Documents/EasySpin/workflows/examples/major_project_tranche_continue_from_approved_design_v2_call.yaml`
- Optional sync target: `/home/ollie/Documents/EasySpin/workflows/library/scripts/publish_major_project_continue_outcome.py`

- [ ] **Step 1: Sync only after canonical tests pass**

If EasySpin still consumes checked-in copies of these workflows, copy the changed workflow files from this repo into the downstream EasySpin paths. Do not copy test-only files unless EasySpin carries its own test suite for these workflows.

- [ ] **Step 2: Run an EasySpin workflow smoke check in `ptycho311`**

From `/home/ollie/Documents/EasySpin`, use `tmux` for long-running commands and run in the `ptycho311` environment. Prefer the repo's existing invocation style:

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate ptycho311
python -m orchestrator report <run_id>
```

For reruns after this fix, prefer:

```bash
python -m orchestrator resume <failed_run_id>
```

over launching a fresh run when the earlier run has already passed approval/review gates.

- [ ] **Step 3: Confirm the specific crash is gone**

Inspect the resumed run. Expected: after `ESCALATE_REDESIGN`, `current_phase=big_design` is accepted by the stack and routed to `RunBigDesignPhase`. If the run later fails on numerical acceptance, that is a legitimate project implementation/review failure and should be handled by the normal redesign/replan/roadmap escalation ladder, not by this workflow-routing fix.

## Acceptance Criteria

- Approved-design continuation can start at `plan` without rerunning big design.
- If plan review returns `ESCALATE_REDESIGN`, the same workflow routes into `big_design` without output-contract failure.
- If redesign approves, the workflow returns to plan and then implementation using current visit roots.
- If redesign returns `ESCALATE_ROADMAP_REVISION`, the approved-design wrapper reports a controlled blocked/terminal outcome and does not call manifest update as though the tranche had simply completed or skipped.
- There is one authoritative phase router for major-project tranche execution; the approved-design path delegates to it instead of maintaining a partial duplicate.
- Static tests catch future drift between route helpers that can write `current_phase` values and workflows that read/route those values.
