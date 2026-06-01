# Design Delta Blocker Revision Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the design-delta Lisp frontend drain route implementation blockers that can be resolved by design changes into a reviewed target-design revision, then continue the drain instead of terminating immediately as blocked.

**Architecture:** Keep deterministic routing in workflow YAML and scripts. Provider steps may propose, edit, and review the target `.md`; workflow steps classify blocker safety, enforce bounded revision attempts, validate provider output contracts, and either emit `CONTINUE` for a new planning pass or record a terminal block. This first slice covers the design-delta stack because it has an explicit `target_design_path`; the shared full/MVP stack remains unchanged until this route is proven.

**Tech Stack:** agent-orchestration DSL v2.14 YAML, Python command adapters under `workflows/library/scripts/`, provider prompt assets under `workflows/library/prompts/`, pytest runtime/workflow tests.

---

## Required Context

Read before implementation:

- `docs/index.md`
- `docs/workflow_drafting_guide.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/providers.md`
- `workflows/README.md`
- `docs/design/lisp_frontend_review_fix_loops.md`
- `docs/design/workflow_command_adapter_contract.md`

Repo constraints:

- Do not create a worktree.
- Keep prompts local to provider judgment/editing. Routing, loop counters, safety classification, and terminal state belong in workflow/script contracts.
- Do not parse markdown reports for semantic routing. If blocker fields are needed, read `implementation_state.json` through a structured adapter.
- For workflow changes, run both narrow pytest selectors and an orchestrator dry-run.

## File Structure

- Modify: `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml`
  - Adds the implementation-blocker revision branch and returns `CONTINUE` when target design revision is approved.
- Create: `workflows/library/scripts/classify_lisp_frontend_implementation_blocker.py`
  - Reads implementation-state JSON and work-item metadata, emits a typed route for revision-allowed versus terminal blockers.
- Modify: `workflows/library/scripts/update_lisp_frontend_run_state.py`
  - Adds a nonterminal `design_revision` event writer that records design-revision history and writes `drain_status=CONTINUE`.
- Create: `workflows/library/prompts/lisp_frontend_design_delta_work_item/revise_target_design_for_blocker.md`
  - Provider prompt for revising the target design from blocker evidence.
- Create: `workflows/library/prompts/lisp_frontend_design_delta_work_item/review_target_design_revision.md`
  - Provider prompt for approving or requesting one more target-design revision.
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`
  - Adds script-level and runtime tests for allowed blocker revision, denied blocker terminal block, and bounded review behavior.
- Optionally modify: `workflows/README.md`
  - Only if the design-delta workflow catalog description needs the new route noted.

## Behavioral Contract

Implementation blockers split into typed routes:

```text
roadmap_conflict -> DESIGN_REVISION_ALLOWED
user_decision_required -> TERMINAL_BLOCK
external_dependency_outside_authority -> TERMINAL_BLOCK
missing_resource -> TERMINAL_BLOCK
unavailable_hardware -> TERMINAL_BLOCK
unrecoverable_after_fix_attempt -> TERMINAL_BLOCK
```

`DESIGN_REVISION_ALLOWED` means the implementation produced evidence that the current target design or implementation architecture is inconsistent with the work item. It does not mean the provider can silently broaden scope. The design revision must be reviewed before the drain continues.

After an approved target-design revision:

- record a run-state history event;
- write a summary artifact for the item with status `DESIGN_REVISED`;
- write `drain_status=CONTINUE`;
- do not record the item as completed or blocked;
- let the top-level drain run the next selector/planning iteration from the revised target design.

If the design-revision review exhausts its budget or returns a terminal non-approval, record `BLOCKED` with reason `design_revision_exhausted`.

## Task 1: Add Blocker Classification Adapter

**Files:**

- Create: `workflows/library/scripts/classify_lisp_frontend_implementation_blocker.py`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Write failing tests for blocker classification**

Add tests near existing script tests:

```python
def test_classify_implementation_blocker_allows_roadmap_conflict(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = workspace / "state/implementation_state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps({"implementation_state": "BLOCKED", "blocker_class": "roadmap_conflict"}) + "\n",
        encoding="utf-8",
    )
    output_path = workspace / "state/blocker-route.json"

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/classify_lisp_frontend_implementation_blocker.py"),
        "--implementation-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--work-item-source",
        "DESIGN_GAP",
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload == {
        "blocker_route": "DESIGN_REVISION_ALLOWED",
        "blocker_class": "roadmap_conflict",
        "block_reason": "implementation_design_revision_required",
    }
```

Add a second test proving `user_decision_required` produces `TERMINAL_BLOCK`.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "classify_implementation_blocker" -q
```

Expected: fails because the script does not exist.

- [ ] **Step 3: Implement the adapter**

Create `workflows/library/scripts/classify_lisp_frontend_implementation_blocker.py`:

```python
#!/usr/bin/env python3
"""Classify whether a Lisp frontend implementation blocker can revise design."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REVISION_ALLOWED = {"roadmap_conflict"}
BLOCKED_CLASSES = {
    "missing_resource",
    "unavailable_hardware",
    "roadmap_conflict",
    "external_dependency_outside_authority",
    "user_decision_required",
    "unrecoverable_after_fix_attempt",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation-state-path", required=True)
    parser.add_argument("--work-item-source", required=True, choices=["BACKLOG_ITEM", "DESIGN_GAP"])
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload = json.loads(Path(args.implementation_state_path).read_text(encoding="utf-8"))
    if payload.get("implementation_state") != "BLOCKED":
        raise SystemExit("Implementation blocker classifier requires BLOCKED implementation_state")
    blocker_class = str(payload.get("blocker_class") or "").strip()
    if blocker_class not in BLOCKED_CLASSES:
        raise SystemExit(f"Unexpected blocker_class: {blocker_class}")

    if args.work_item_source == "DESIGN_GAP" and blocker_class in REVISION_ALLOWED:
        route = "DESIGN_REVISION_ALLOWED"
        reason = "implementation_design_revision_required"
    else:
        route = "TERMINAL_BLOCK"
        reason = "implementation_blocked"

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {"blocker_route": route, "blocker_class": blocker_class, "block_reason": reason},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "classify_implementation_blocker" -q
```

Expected: classifier tests pass.

- [ ] **Step 5: Commit**

```bash
git add workflows/library/scripts/classify_lisp_frontend_implementation_blocker.py tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "test: classify design-revisable implementation blockers"
```

## Task 2: Add Run-State Support For Nonterminal Design Revisions

**Files:**

- Modify: `workflows/library/scripts/update_lisp_frontend_run_state.py`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Write failing script test**

Add a test that invokes:

```bash
python workflows/library/scripts/update_lisp_frontend_run_state.py \
  --state-path state/run_state.json \
  design_revision \
  --item-id parser-syntax \
  --source DESIGN_GAP \
  --reason implementation_design_revision_required \
  --summary-path artifacts/work/parser-syntax-summary.json \
  --summary-pointer-path state/item_summary_path.txt \
  --drain-status-path state/drain_status.txt
```

Assert:

```python
state = json.loads((workspace / "state/run_state.json").read_text())
assert state["history"][-1]["event"] == "design_revision"
assert "parser-syntax" not in state["completed_design_gaps"]
assert "parser-syntax" not in state["blocked_design_gaps"]
assert (workspace / "state/drain_status.txt").read_text().strip() == "CONTINUE"
summary = json.loads((workspace / "artifacts/work/parser-syntax-summary.json").read_text())
assert summary["item_status"] == "DESIGN_REVISED"
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "design_revision" -q
```

Expected: fails because `design_revision` is not a supported subcommand.

- [ ] **Step 3: Implement `design_revision` subcommand**

Extend `update_lisp_frontend_run_state.py` with:

- a `design_revision` subparser;
- required `--item-id`, `--source`, `--reason`;
- optional summary and drain-status paths mirroring `complete`/`blocked`;
- a history event only, with no completed/blocked mutation;
- summary JSON:

```json
{
  "work_item_id": "...",
  "work_item_source": "DESIGN_GAP",
  "item_status": "DESIGN_REVISED",
  "reason": "implementation_design_revision_required",
  "run_state_path": "state/..."
}
```

- [ ] **Step 4: Run test to verify pass**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "design_revision" -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add workflows/library/scripts/update_lisp_frontend_run_state.py tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "feat: record design revision drain events"
```

## Task 3: Add Design-Revision Prompts

**Files:**

- Create: `workflows/library/prompts/lisp_frontend_design_delta_work_item/revise_target_design_for_blocker.md`
- Create: `workflows/library/prompts/lisp_frontend_design_delta_work_item/review_target_design_revision.md`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add prompt existence/content tests**

Add a test that reads both prompt files and asserts they use target/baseline language and do not tell the provider to manage workflow routing:

```python
def test_design_delta_blocker_revision_prompts_keep_roles_clear():
    prompt_paths = [
        ROOT / "workflows/library/prompts/lisp_frontend_design_delta_work_item/revise_target_design_for_blocker.md",
        ROOT / "workflows/library/prompts/lisp_frontend_design_delta_work_item/review_target_design_revision.md",
    ]
    for path in prompt_paths:
        text = path.read_text(encoding="utf-8").lower()
        assert "target design" in text
        assert "baseline design" in text
        assert "workflow owns" not in text
        assert "drain loop" not in text
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "blocker_revision_prompts" -q
```

Expected: fails because prompt files do not exist.

- [ ] **Step 3: Write reviser prompt**

Create `revise_target_design_for_blocker.md` with concise instructions:

```markdown
You are revising the target design document because implementation found a
blocking contract or roadmap conflict.

Read the consumed target design, baseline design, approved plan, and blocker
progress report. Update only the target design document. Keep the baseline
document unchanged.

Make the smallest principled design change that resolves the blocker. If the
blocker cannot be resolved by changing the target design, write a revision
report explaining why and set the decision to `BLOCKED`.

Write:
- the updated target design at the consumed target design path;
- a JSON revision report at the required output path.

The report JSON must contain this shape:

    {
      "design_revision_decision": "REVISED | BLOCKED",
      "summary": "",
      "changed_sections": [],
      "blocker_class": "",
      "reason": ""
    }
```

- [ ] **Step 4: Write reviewer prompt**

Create `review_target_design_revision.md`:

```markdown
You are reviewing whether the revised target design resolves the implementation
blocker without weakening the baseline compatibility contract.

Read the consumed target design, baseline design, approved plan, blocker
progress report, and revision report. Decide `APPROVE` if the target design now
provides a coherent contract for replanning. Decide `REVISE` if a bounded
follow-up edit to the target design should fix a concrete issue.

Write the review report at the required output path and the review decision at
the required decision path.
```

- [ ] **Step 5: Run prompt tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "blocker_revision_prompts" -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add workflows/library/prompts/lisp_frontend_design_delta_work_item tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "docs: add design blocker revision prompts"
```

## Task 4: Wire The Design-Delta Work-Item Revision Branch

**Files:**

- Modify: `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add workflow-structure test**

Add a test that loads `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml` and asserts:

- imports remain plan/implementation only;
- `ClassifyImplementationBlocker` exists under the `IMPLEMENTATION_BLOCKED` case;
- `DESIGN_REVISION_ALLOWED` branch includes `ReviseTargetDesignForBlocker`, `ReviewTargetDesignRevisionLoop`, and `RecordDesignRevisionForRetry`;
- `RecordDesignRevisionForRetry` writes `drain_status=CONTINUE`;
- terminal-block path still calls `update_lisp_frontend_run_state.py blocked`.

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "design_delta_work_item_revision_branch" -q
```

Expected: fails because branch does not exist.

- [ ] **Step 3: Add workflow artifacts and outputs**

In `lisp_frontend_design_delta_work_item.v214.yaml`, add artifacts for:

- `progress_report` pointer from implementation phase state root;
- `design_revision_report`;
- `design_revision_review_report`;
- `design_revision_review_decision`.

Keep output type of the work-item workflow unchanged: `drain_status` and `item_summary_path`.

- [ ] **Step 4: Replace `IMPLEMENTATION_BLOCKED` terminal body with typed route**

Inside the existing `IMPLEMENTATION_BLOCKED` match case:

1. Run `ClassifyImplementationBlocker`:

```yaml
- name: ClassifyImplementationBlocker
  id: classify_implementation_blocker
  command:
    - python
    - workflows/library/scripts/classify_lisp_frontend_implementation_blocker.py
    - --implementation-state-path
    - ${steps.ResolveWorkItemInputs.artifacts.implementation_phase_state_root}/implementation_state.json
    - --work-item-source
    - ${steps.ResolveWorkItemInputs.artifacts.work_item_source}
    - --output
    - ${inputs.state_root}/implementation-blocker-route.json
  output_bundle:
    path: ${inputs.state_root}/implementation-blocker-route.json
    fields:
      - name: blocker_route
        json_pointer: /blocker_route
        type: enum
        allowed: ["DESIGN_REVISION_ALLOWED", "TERMINAL_BLOCK"]
      - name: blocker_class
        json_pointer: /blocker_class
        type: enum
        allowed:
          - missing_resource
          - unavailable_hardware
          - roadmap_conflict
          - external_dependency_outside_authority
          - user_decision_required
          - unrecoverable_after_fix_attempt
      - name: block_reason
        json_pointer: /block_reason
        type: enum
        allowed: ["implementation_design_revision_required", "implementation_blocked"]
```

2. Match `blocker_route`.
3. Keep the current `RecordImplementationBlocked` command in `TERMINAL_BLOCK`.
4. Add `DESIGN_REVISION_ALLOWED` branch with the steps below.

- [ ] **Step 5: Add bounded design-revision review loop**

In `DESIGN_REVISION_ALLOWED`:

- `ReviseTargetDesignForBlocker` provider consumes target design, baseline design, plan, and progress report.
- It writes a JSON revision report at `${inputs.state_root}/design-revision-report.json`.
- `ReviewTargetDesignRevisionLoop` repeats up to 3 times until decision `APPROVE`.
- On `REVISE`, run `ReviseTargetDesignForBlocker` again, consuming the review report.
- On exhaustion, route to blocked with reason `design_revision_exhausted`.

Use `output_bundle` or `expected_outputs` for the review decision and report. Do not ask the prompt to decide whether the drain continues.

- [ ] **Step 6: Add retry record step**

After review approval, run:

```yaml
- name: RecordDesignRevisionForRetry
  id: record_design_revision_for_retry
  command:
    - python
    - workflows/library/scripts/update_lisp_frontend_run_state.py
    - --state-path
    - ${inputs.run_state_path}
    - design_revision
    - --item-id
    - ${steps.ResolveWorkItemInputs.artifacts.work_item_id}
    - --source
    - ${steps.ResolveWorkItemInputs.artifacts.work_item_source}
    - --reason
    - implementation_design_revision_required
    - --summary-path
    - ${steps.ResolveWorkItemInputs.artifacts.item_summary_target_path}
    - --summary-pointer-path
    - ${inputs.state_root}/item_summary_path.txt
    - --drain-status-path
    - ${inputs.state_root}/drain_status.txt
  expected_outputs: *terminal_outputs
```

Make the `IMPLEMENTATION_BLOCKED` case outputs read from the nested route branch, not directly from `RecordImplementationBlocked`.

- [ ] **Step 7: Run workflow-structure test**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "design_delta_work_item_revision_branch" -q
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add workflows/library/lisp_frontend_design_delta_work_item.v214.yaml tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "feat: route design-delta blockers to design revision"
```

## Task 5: Add Runtime Coverage For Revision And Terminal Block Paths

**Files:**

- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Extend the runtime test helper for design-delta inputs**

Change `_run_workflow_with_providers(...)` to accept optional
`workflow_inputs`:

```python
def _run_workflow_with_providers(
    workspace: Path,
    workflow_path: Path,
    provider_sequence,
    require_all_providers: bool = True,
    workflow_inputs: dict | None = None,
):
    ...
    bound_inputs = bind_workflow_inputs(
        workflow_input_contracts(workflow),
        workflow_inputs or _workflow_inputs(),
        workspace,
    )
```

Add:

```python
def _design_delta_workflow_inputs() -> dict:
    return {
        "steering_path": "docs/steering.md",
        "target_design_path": "docs/design/workflow_lisp_frontend_specification.md",
        "baseline_design_path": "docs/design/workflow_lisp_frontend_mvp_specification.md",
        "progress_ledger_path": "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json",
    }
```

Design-delta runtime tests must pass
`workspace / "workflows/examples/lisp_frontend_design_delta_drain.yaml"` and
`workflow_inputs=_design_delta_workflow_inputs()`.

- [ ] **Step 2: Add provider writers**

Add helpers:

```python
def _write_blocked_roadmap_conflict(workspace: Path) -> None:
    for root in sorted(workspace.glob("state/**/implementation-phase")):
        bundle_path = root / "implementation_state.json"
        if bundle_path.exists():
            continue
        progress_pointer = root / "progress_report_target_path.txt"
        target = workspace / progress_pointer.read_text(encoding="utf-8").strip()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Progress Report\n\nBlocked by design conflict.\n", encoding="utf-8")
        bundle_path.write_text(
            json.dumps({"implementation_state": "BLOCKED", "blocker_class": "roadmap_conflict"}, indent=2) + "\n",
            encoding="utf-8",
        )
        return
    raise AssertionError("No pending implementation phase root found")


def _write_blocked_user_decision_required(workspace: Path) -> None:
    for root in sorted(workspace.glob("state/**/implementation-phase")):
        bundle_path = root / "implementation_state.json"
        if bundle_path.exists():
            continue
        progress_pointer = root / "progress_report_target_path.txt"
        target = workspace / progress_pointer.read_text(encoding="utf-8").strip()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Progress Report\n\nBlocked pending user decision.\n", encoding="utf-8")
        bundle_path.write_text(
            json.dumps(
                {"implementation_state": "BLOCKED", "blocker_class": "user_decision_required"},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return
    raise AssertionError("No pending implementation phase root found")
```

Add revision/review writers that edit the target design and approve:

```python
def _revise_target_design_for_blocker(workspace: Path) -> None:
    target = workspace / "docs/design/workflow_lisp_frontend_specification.md"
    target.write_text(target.read_text(encoding="utf-8") + "\n\n## Blocker Revision\n\nAdded missing contract.\n", encoding="utf-8")
    report = workspace / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-work-item/design-revision-report.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"design_revision_decision": "REVISED", "summary": "updated"}) + "\n", encoding="utf-8")
```

Use the target path from `_design_delta_workflow_inputs()["target_design_path"]`
when editing the design.

- [ ] **Step 3: Add allowed-blocker runtime test**

Test sequence:

```python
[
    ("SelectNextWork", _write_selector_design_gap),
    ("DraftDesignGapArchitecture", _write_design_gap_architecture),
    ("DraftPlan", _write_plan),
    ("ReviewPlan", _write_plan_review),
    ("ExecuteImplementation", _write_blocked_roadmap_conflict),
    ("ReviseTargetDesignForBlocker", _revise_target_design_for_blocker),
    ("ReviewTargetDesignRevision", _write_design_revision_review_approve),
    ("SelectNextWork", _write_selector_done),
],
workflow_inputs=_design_delta_workflow_inputs(),
```

Assert:

- run completes;
- summary `drain_status` is `DONE` after selector returns done;
- run-state history contains `design_revision`;
- no blocked design gap was recorded for `parser-syntax`;
- target design contains the added blocker revision text.

- [ ] **Step 4: Add denied-blocker runtime test**

Use `user_decision_required` from `ExecuteImplementation`.

Assert:

- no `ReviseTargetDesignForBlocker` provider was called;
- summary `drain_status` is `BLOCKED`;
- blocked design gap reason remains `implementation_blocked`.

- [ ] **Step 5: Run focused runtime tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "design_revision or implementation_blocker" -q
```

Expected: all new tests pass.

- [ ] **Step 6: Run existing adjacent regressions**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "design_gap_runtime_smoke or plan_review_revise or implementation_review_revise or implementation_review_exhaustion or plan_review_exhaustion" -q
```

Expected: existing behavior remains green.

- [ ] **Step 7: Commit**

```bash
git add tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "test: cover design blocker revision routing"
```

## Task 6: Validate Workflow Loading And Dry-Run

**Files:**

- Modify only if needed: `tests/test_lisp_frontend_autonomous_drain_runtime.py`
- Modify only if needed: `workflows/README.md`

- [ ] **Step 1: Run collect-only for changed tests**

Run:

```bash
python -m pytest --collect-only tests/test_lisp_frontend_autonomous_drain_runtime.py -q
```

Expected: collection succeeds.

- [ ] **Step 2: Run the full workflow runtime test module**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q
```

Expected: module passes.

- [ ] **Step 3: Run orchestrator dry-runs**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml \
  --dry-run \
  --input steering_path=docs/steering.md \
  --input target_design_path=docs/design/workflow_lisp_key_migration_parity_architecture.md \
  --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md \
  --input progress_ledger_path=state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json \
  --input drain_state_root=state/LISP-MIGRATION-PARITY-DRAIN/dry-run-drain \
  --input run_state_target_path=state/LISP-MIGRATION-PARITY-DRAIN/dry-run-drain/run_state.json \
  --input drain_summary_target_path=artifacts/work/LISP-MIGRATION-PARITY-DRAIN/dry-run-drain-summary.json \
  --input artifact_work_root=artifacts/work/LISP-MIGRATION-PARITY-DRAIN \
  --input artifact_checks_root=artifacts/checks/LISP-MIGRATION-PARITY-DRAIN \
  --input artifact_review_root=artifacts/review/LISP-MIGRATION-PARITY-DRAIN
```

Expected: validation/dry-run succeeds without launching providers.

- [ ] **Step 4: Inspect workflow/prompt diff together**

Run:

```bash
git diff -- workflows/library/lisp_frontend_design_delta_work_item.v214.yaml \
  workflows/library/prompts/lisp_frontend_design_delta_work_item \
  workflows/library/scripts \
  tests/test_lisp_frontend_autonomous_drain_runtime.py
```

Confirm:

- blocker classification is deterministic;
- provider prompts only revise/review target design content;
- `CONTINUE` is emitted only after approved design revision;
- terminal blockers still record blocked state.

- [ ] **Step 5: Commit any validation/doc cleanup**

```bash
git add workflows/README.md tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "docs: document design blocker revision route"
```

Skip this commit if no docs/cleanup changes were needed.

## Non-Goals

- Do not modify the shared `lisp_frontend_work_item.v214.yaml` full/MVP stack in this slice.
- Do not add a generic roadmap-revision workflow family.
- Do not let provider prompts decide whether the drain continues or blocks.
- Do not silently retry implementation after a blocked result without a reviewed target-design revision.
- Do not alter `lisp_frontend_implementation_phase.v214.yaml` blocker classes unless tests prove a contract mismatch.

## Handoff Notes

This plan intentionally returns `CONTINUE` after a reviewed design revision instead of trying to resume inside the same work-item call. That keeps the change minimal and uses the existing top-level drain loop to reselect/replan from updated target design state. If later behavior needs guaranteed same-item replay, add a second design for an inner work-item attempt loop with per-attempt state roots.
