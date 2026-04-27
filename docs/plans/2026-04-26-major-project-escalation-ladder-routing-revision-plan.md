# Major-Project Escalation Ladder Routing Revision Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not create a git worktree in this repository.

**Goal:** Revise the major-project escalation ladder so upward routing is adjacent-only and roadmap-revision dispatch is implemented through a DSL-valid drain-iteration boundary.

**Architecture:** Keep provider judgment phase-local: implementation may escalate only to planning, planning may escalate only to design, and design may escalate only to roadmap revision. Move one drain iteration into a reusable workflow so the parent repeat loop calls a single iteration unit while the iteration workflow owns top-level selection and outcome routing. Keep roadmap/manifest mutation deterministic and fail closed when roadmap revision cannot be completed.

**Tech Stack:** Agent-orchestration DSL v2.7, reusable `call` workflows, top-level `match`, `repeat_until`, deterministic Python helper scripts, major-project-local prompt assets, pytest workflow contract tests, and orchestrator dry-run validation.

---

## Current Issues

1. Implementation review currently has too much upward authority.
   It can emit `ESCALATE_REDESIGN`, which skips the plan phase even though the plan phase owns the executable-work contract. This makes implementation review decide whether a failure is plan-local or design-level.

2. Roadmap-revision routing is only partially implemented.
   The selected tranche stack can surface `ESCALATE_ROADMAP_REVISION`, but the drain workflow does not dispatch the roadmap revision phase. A direct nested `match` inside the current `repeat_until` shape is rejected by DSL v2.7.

3. Manifest update currently accepts `ESCALATE_ROADMAP_REVISION` as a continuing outcome.
   Without drain-level dispatch, that can reselect the same tranche and churn. Roadmap escalation should either run roadmap revision or block explicitly.

## Target Semantics

Use one-step upward escalation:

```text
implementation review
  -> APPROVE | REVISE | ESCALATE_REPLAN | BLOCK

plan review
  -> APPROVE | REVISE | ESCALATE_REDESIGN | BLOCK

design review
  -> APPROVE | REVISE | ESCALATE_ROADMAP_REVISION | BLOCK
```

Implementation may write evidence saying the issue appears design-level, but its routing decision remains `ESCALATE_REPLAN`. The plan phase consumes that evidence and decides whether to repair the plan or escalate to redesign.

Roadmap revision runs only after design review emits `ESCALATE_ROADMAP_REVISION`. The drain must not mark the tranche completed, skipped, or still-pending by manifest update before the roadmap revision phase has approved or blocked.

## Workflow Shape

Introduce a reusable one-iteration workflow:

- `workflows/library/major_project_tranche_drain_iteration.yaml`

The parent drain workflow becomes:

```text
RunRoadmapPhase
DrainManifest repeat_until:
  RunDrainIteration
PublishDrainSummary
```

`RunDrainIteration` owns top-level routing:

```text
SelectNextTranche
RouteSelection match selection_status:
  SELECTED -> RunSelectedTranche, output iteration_route = item_outcome
  DONE -> output iteration_route = DONE
  BLOCKED -> output iteration_route = BLOCKED

RouteIterationOutcome match iteration_route:
  APPROVED/SKIPPED/BLOCKED item outcomes -> UpdateTrancheManifest
  ESCALATE_ROADMAP_REVISION -> RunRoadmapRevisionPhase, PromoteApprovedRoadmapRevision
  DONE -> WriteDrainDone
  BLOCKED -> WriteDrainBlocked
```

This keeps both `match` statements top-level in the iteration workflow, avoiding nested structured control inside the parent repeat body.

## Roadmap And Manifest Authority

The drain owns stable current paths:

- current project roadmap: the bound `project_roadmap_target_path`
- current tranche manifest: the bound `tranche_manifest_target_path`

Roadmap revision should write candidates first:

- `${drain_state_root}/iterations/${loop.index}/roadmap-revision/project-roadmap.candidate.md`
- `${drain_state_root}/iterations/${loop.index}/roadmap-revision/tranche-manifest.candidate.json`

After approval, a deterministic command promotes candidates to the stable current paths. The next drain iteration selects from the updated manifest and roadmap.

If roadmap revision blocks, the iteration returns `drain_status=BLOCKED` and records the roadmap revision report. It must not silently continue.

## Required Code Changes

### Task 1: Revise The Existing Design And Plan Documents

**Files:**

- Modify: `docs/plans/2026-04-26-major-project-implementation-escalation-ladder-design.md`
- Modify: `docs/plans/2026-04-26-major-project-implementation-escalation-ladder-implementation-plan.md`

- [ ] Replace implementation review decisions with `APPROVE`, `REVISE`, `ESCALATE_REPLAN`, and `BLOCK`.
- [ ] Remove direct implementation-to-redesign routing from the design and plan.
- [ ] Add the drain-iteration workflow boundary as the required fix for roadmap-revision dispatch.
- [ ] State that `ESCALATE_ROADMAP_REVISION` is handled by the drain iteration, not by the manifest update script.

### Task 2: Update Implementation Phase Contracts

**Files:**

- Modify: `workflows/library/major_project_tranche_implementation_phase.yaml`
- Modify: `workflows/library/prompts/major_project_stack/review_implementation.md`
- Modify: `workflows/library/prompts/major_project_stack/fix_implementation.md`
- Modify: `tests/test_major_project_workflows.py`

- [ ] Change allowed implementation review decisions to `["APPROVE", "REVISE", "ESCALATE_REPLAN", "BLOCK"]`.
- [ ] Update implementation review guidance so suspected design-level problems are recorded as evidence in the `ESCALATE_REPLAN` context, not routed directly to design.
- [ ] Add or update tests asserting the implementation phase does not expose `ESCALATE_REDESIGN`.
- [ ] Preserve the cumulative implementation iteration context and threshold behavior.

### Task 3: Update Selected-Tranche Stack Routing

**Files:**

- Modify: `workflows/library/major_project_tranche_design_plan_impl_stack.yaml`
- Modify: `workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml`
- Modify: `tests/test_major_project_workflows.py`

- [ ] Remove `AssertImplementationEscalateRedesign` and `ActivateImplementationEscalationForRedesign`.
- [ ] Route implementation `ESCALATE_REPLAN` to `RunPlanPhase` after activating upstream context.
- [ ] Route implementation `BLOCK` to a blocked/skipped implementation outcome that manifest update can mark `blocked`.
- [ ] Keep plan `ESCALATE_REDESIGN` as the only route back to `RunBigDesignPhase`.
- [ ] Keep design `ESCALATE_ROADMAP_REVISION` as an item outcome surfaced to the drain.

### Task 4: Add One-Iteration Drain Workflow

**Files:**

- Create: `workflows/library/major_project_tranche_drain_iteration.yaml`
- Modify: `tests/test_major_project_workflows.py`

- [ ] Move selection, selected-stack execution, manifest update, and roadmap-revision dispatch into the iteration workflow.
- [ ] Use a top-level `match` for `selection_status`.
- [ ] Use a second top-level `match` for the normalized iteration route.
- [ ] Import and call `major_project_roadmap_revision_phase.yaml` only in the `ESCALATE_ROADMAP_REVISION` case.
- [ ] Promote approved roadmap/manifest candidates deterministically after roadmap revision approval.
- [ ] Return `drain_status` as `CONTINUE`, `DONE`, or `BLOCKED`.

### Task 5: Simplify Parent Drain Workflows

**Files:**

- Modify: `workflows/examples/major_project_tranche_drain_stack_v2_call.yaml`
- Modify: `workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml`
- Modify: `tests/test_major_project_workflows.py`

- [ ] Import `major_project_tranche_drain_iteration.yaml`.
- [ ] Replace the current repeat body with one `call` to the iteration workflow.
- [ ] Set the repeat output from the iteration workflow `drain_status`.
- [ ] Keep `RunRoadmapPhase` and `PublishDrainSummary` in the parent drain workflow.
- [ ] Ensure both drain workflows validate with `orchestrator run ... --dry-run`.

### Task 6: Fail Closed In Manifest Update

**Files:**

- Modify: `workflows/library/scripts/update_major_project_tranche_manifest.py`
- Modify: `tests/test_major_project_manifest_validator.py`

- [ ] Stop treating `ESCALATE_ROADMAP_REVISION` as a normal manifest update outcome.
- [ ] If the manifest update script receives `ESCALATE_ROADMAP_REVISION`, return a blocked/error result explaining that roadmap revision must be dispatched before manifest update.
- [ ] Keep `superseded` as a valid manifest status for approved roadmap revisions to use.

### Task 7: Verification

**Files:**

- Modify: tests only as needed.

- [ ] Run:

```bash
pytest --collect-only tests/test_major_project_workflows.py tests/test_major_project_manifest_validator.py tests/test_major_project_escalation_state.py
```

- [ ] Run:

```bash
pytest tests/test_major_project_escalation_state.py tests/test_major_project_manifest_validator.py tests/test_major_project_workflows.py -q
```

- [ ] Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/major_project_tranche_drain_stack_v2_call.yaml --dry-run
```

- [ ] Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml --dry-run --input project_brief_path=workflows/examples/inputs/major_project_brief.md --input project_roadmap_path=docs/plans/major-project-demo/project-roadmap.md --input tranche_manifest_target_path=state/major-project-demo/tranche_manifest.json
```

- [ ] Run:

```bash
pytest tests/test_workflow_examples_v0.py -q
git diff --check
```

## Non-Goals

- Do not change the shared generic plan or implementation phases.
- Do not add prompt text that teaches providers workflow internals.
- Do not make implementation review directly authorize redesign or roadmap revision.
- Do not use manifest update as a substitute for roadmap-revision dispatch.

## Acceptance Criteria

- Implementation phase has no `ESCALATE_REDESIGN` decision.
- Implementation escalation always routes to plan first.
- Plan escalation is the only route from plan to design.
- Design escalation is the only route to roadmap revision.
- Parent drain workflows contain no nested roadmap-revision routing inside the repeat body.
- Roadmap revision dispatch is handled by a reusable top-level iteration workflow.
- `ESCALATE_ROADMAP_REVISION` cannot cause silent manifest churn.
- Unit tests and orchestrator dry-run checks pass.
