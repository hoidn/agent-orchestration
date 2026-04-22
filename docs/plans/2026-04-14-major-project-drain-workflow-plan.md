# Major Project Drain Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a runnable major-project drain workflow that generates the roadmap once, then repeatedly selects and executes ready tranches from the generated manifest until the manifest is complete or blocked.

**Architecture:** Keep roadmap generation outside the loop. Put only deterministic tranche selection, one selected tranche stack call, and manifest status update inside a bounded `repeat_until` loop. Use small library scripts for manifest selection and manifest update so routing and status mutation are deterministic and testable.

**Tech Stack:** Agent-orchestration DSL v2.7, Python helper scripts under `workflows/library/scripts/`, existing major-project roadmap and tranche stack library workflows, pytest runtime smoke tests with mocked providers.

---

### Task 1: Add failing workflow and helper tests

**Files:**
- Modify: `tests/test_major_project_workflows.py`
- Modify: `tests/test_workflow_examples_v0.py`

- [x] Add loader/shape assertions for a new `workflows/examples/major_project_tranche_drain_stack_v2_call.yaml`.
- [x] Add a mocked-provider runtime test with two manifest tranches that proves `RunRoadmapPhase` runs once and the drain loop executes both tranches through manifest update.
- [x] Add the new example to the example-load registry.
- [x] Run: `pytest tests/test_major_project_workflows.py -k drain -v`
- [x] Expected: fail because the drain workflow and helper scripts do not exist yet.

### Task 2: Add deterministic manifest helper scripts

**Files:**
- Create: `workflows/library/scripts/select_major_project_tranche.py`
- Create: `workflows/library/scripts/update_major_project_tranche_manifest.py`

- [x] Implement selection of the first `pending` tranche whose prerequisites have completed.
- [x] Emit `SELECTED`, `DONE`, or `BLOCKED` plus typed handoff fields in an output bundle.
- [x] Update the manifest after a selected tranche completes: `APPROVED` marks the tranche `completed`; skipped outcomes mark it `blocked`.
- [x] Emit `CONTINUE` for approved tranches and `BLOCKED` for skipped tranches.

### Task 3: Add the drain workflow

**Files:**
- Create: `workflows/examples/major_project_tranche_drain_stack_v2_call.yaml`
- Modify: `workflows/README.md`

- [x] Import `major_project_roadmap_phase.yaml` and `major_project_tranche_design_plan_impl_stack.yaml`.
- [x] Run `RunRoadmapPhase` once before the drain loop.
- [x] Inside `DrainManifest`, run `SelectNextTranche`, route `SELECTED|DONE|BLOCKED`, call the tranche stack only for `SELECTED`, then update the manifest.
- [x] Stop the loop when the loop-frame `drain_status` is `DONE` or `BLOCKED`.
- [x] Publish a final drain summary path.
- [x] Index the new workflow in `workflows/README.md`.

### Task 4: Verify

**Files:**
- No new files.

- [x] Run: `pytest --collect-only tests/test_major_project_workflows.py tests/test_workflow_examples_v0.py -q`
- [x] Run: `pytest tests/test_major_project_workflows.py -v`
- [x] Run: `pytest tests/test_workflow_examples_v0.py::test_workflow_examples_v0_load -v`
- [x] Run an orchestrator dry run for the new example:
  `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/major_project_tranche_drain_stack_v2_call.yaml --dry-run`
