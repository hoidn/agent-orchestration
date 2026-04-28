# Major-Project Phase Re-Entry Write Roots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make major-project tranche phase re-entry legal under reusable-call write-root rules by allocating a fresh DSL-managed phase state root for every upward re-entry.

**Architecture:** The selected-tranche stack owns phase visit allocation, lineage, and routing. Each reusable phase call receives a unique `state_root` from a deterministic phase-visit allocator, while stable human-facing artifact paths such as `design_target_path`, `plan_target_path`, and review report target paths remain unchanged. Escalation context remains the semantic input passed between phases; phase visit roots are runtime state, not prompt-managed behavior.

**Tech Stack:** Workflow DSL v2.7/v2.12, reusable `call`, Python helper scripts under `workflows/library/scripts/`, pytest, orchestrator dry-run/smoke checks.

---

## Problem

The EasySpin workflow failed after implementation review correctly produced `ESCALATE_REPLAN`. The selected-tranche stack routed back to `RunPlanPhase`, but the second call to the plan reusable workflow used the same `state_root` as the first call:

`state/easyspin-pytorch-port/tranche-drain-t26-after-roadmap-escalation-v2/items/easyspin-pytorch-port/T26-full-chili-slow-motion-solver-expansion/implementation-phase/../plan-phase`

The runtime rejected this as `colliding_write_root_binding`. That rejection is correct. The DSL contract requires every DSL-managed reusable workflow write root that must remain distinct across repeated invocations to be exposed as a typed `relpath` input and bound distinctly at each call site.

The workflow bug is not that `ESCALATE_REPLAN` exists. The bug is that upward phase re-entry reuses a call-managed write root.

## Design Principles

- Keep the collision guard intact.
- Treat `ESCALATE_REPLAN` and `ESCALATE_REDESIGN` as normal controlled outcomes, not workflow crashes.
- Allocate a new phase visit root before every reusable phase call.
- Keep durable artifact targets stable unless the workflow intentionally creates a candidate artifact.
- Keep deterministic routing, counters, ledgers, and visit allocation in workflow-owned command steps.
- Keep prompts local to design, plan, implementation, and review judgment. Prompts must not manage visit counters or call roots.
- Make allocation idempotent enough for workflow resume. Re-running an allocation step with the same allocation key should return the same pending visit root instead of minting a duplicate.

## Recommended Approach

Use a parent-owned phase visit allocator.

The tranche stack should continue receiving the existing phase root inputs from selection, but those inputs become base directories for phase visits:

- `${inputs.big_design_phase_state_root}/visits/0000`
- `${inputs.plan_phase_state_root}/visits/0000`
- `${inputs.implementation_phase_state_root}/visits/0000`
- `${inputs.plan_phase_state_root}/visits/0001` after `ESCALATE_REPLAN`
- `${inputs.big_design_phase_state_root}/visits/0001` after `ESCALATE_REDESIGN`

Stable target paths remain unchanged:

- `design_target_path`
- `design_review_report_target_path`
- `plan_target_path`
- `plan_review_report_target_path`
- `execution_report_target_path`
- `implementation_review_report_target_path`
- `item_summary_target_path`

Rejected alternatives:

- Make phase workflows internally re-entrant under one state root. This still aliases call-managed roots and makes resume/state ownership ambiguous.
- Disable or relax `colliding_write_root_binding`. That would hide real corruption risks across repeated calls.
- Ask prompts to choose fresh paths. This moves deterministic workflow control into non-deterministic text generation.

## Target State

Add a phase visit ledger under each item state root:

```json
{
  "schema": "major_project_phase_visits.v1",
  "visits": [
    {
      "phase": "plan",
      "visit_index": 0,
      "allocation_key": "initial-plan",
      "reason": "initial_plan",
      "state_root": "state/project/items/item/plan-phase/visits/0000",
      "status": "allocated",
      "source_context_path": null
    }
  ],
  "current": {
    "big_design": {
      "visit_index": 0,
      "state_root": "state/project/items/item/big-design-phase/visits/0000"
    },
    "plan": {
      "visit_index": 1,
      "state_root": "state/project/items/item/plan-phase/visits/0001"
    },
    "implementation": {
      "visit_index": 0,
      "state_root": "state/project/items/item/implementation-phase/visits/0000"
    }
  }
}
```

The allocator output bundle should expose at least:

```json
{
  "phase": "plan",
  "visit_index": 1,
  "phase_state_root": "state/project/items/item/plan-phase/visits/0001",
  "phase_visit_ledger_path": "state/project/items/item/phase_visit_ledger.json"
}
```

The workflows then bind calls through allocation artifacts:

```yaml
with:
  state_root:
    ref: steps.AllocatePlanVisit.artifacts.phase_state_root
```

All follow-on gate commands that currently read `${inputs.plan_phase_state_root}/final_plan_review_decision.txt` must read from the active allocated root instead. The same applies to design and implementation phase outputs.

## Files

- Create: `workflows/library/scripts/major_project_phase_visits.py`
- Create: `tests/test_major_project_phase_visits.py`
- Modify: `workflows/library/major_project_tranche_design_plan_impl_stack.yaml`
- Modify: `workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml`
- Modify: `tests/test_major_project_workflows.py`
- Modify if needed: `workflows/README.md`
- Modify if needed after plan execution: `docs/index.md`

Do not edit provider prompts for this fix unless a test proves an artifact path instruction is stale. This is a workflow control problem.

## Implementation Tasks

### Task 1: Add allocator unit tests

**Files:**
- Create: `tests/test_major_project_phase_visits.py`

- [ ] **Step 1: Write tests for initial allocation**

Create a test that calls `allocate_phase_visit` for `phase="plan"` with base root `tmp/state/item/plan-phase` and allocation key `initial-plan`.

Expected assertions:

- ledger file exists under `item_state_root/phase_visit_ledger.json`
- returned `phase_state_root` ends with `plan-phase/visits/0000`
- `current.plan.state_root` points at that path
- output bundle mirrors the returned payload

- [ ] **Step 2: Write tests for re-entry allocation**

Allocate `initial-plan`, then allocate `implementation-escalate-replan-1`.

Expected assertions:

- second root ends with `plan-phase/visits/0001`
- ledger contains two plan visits
- stable base root is not used directly as the returned phase root

- [ ] **Step 3: Write resume idempotency test**

Call the allocator twice with the same allocation key.

Expected assertions:

- both calls return the same `phase_state_root`
- the ledger contains one visit for that key

- [ ] **Step 4: Run collect-only**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration pytest --collect-only tests/test_major_project_phase_visits.py
```

Expected: pytest collects the new tests without import errors.

### Task 2: Implement the allocator helper

**Files:**
- Create: `workflows/library/scripts/major_project_phase_visits.py`

- [ ] **Step 1: Add pure functions**

Implement:

- `init_phase_visits(item_state_root: Path, output_bundle: Path | None = None) -> dict`
- `allocate_phase_visit(item_state_root: Path, phase: str, phase_state_root_base: Path, allocation_key: str, reason: str, source_context_path: Path | None = None, output_bundle: Path | None = None) -> dict`

Allowed phases:

- `big_design`
- `plan`
- `implementation`

- [ ] **Step 2: Add CLI commands**

Expose:

```bash
python workflows/library/scripts/major_project_phase_visits.py init --item-state-root ...
python workflows/library/scripts/major_project_phase_visits.py allocate --item-state-root ... --phase plan --phase-state-root-base ... --allocation-key ... --reason ... --output-bundle ...
```

- [ ] **Step 3: Preserve deterministic shape**

Use zero-padded indexes such as `0000`, `0001`, `0002`. Do not include timestamps in fields that tests or workflow routing need. If audit timestamps are added, keep tests shape-based and never route on them.

- [ ] **Step 4: Run unit tests**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration pytest tests/test_major_project_phase_visits.py -q
```

Expected: all allocator tests pass.

### Task 3: Wire the design-plan-implementation stack

**Files:**
- Modify: `workflows/library/major_project_tranche_design_plan_impl_stack.yaml`
- Modify: `tests/test_major_project_workflows.py`

- [ ] **Step 1: Add workflow shape tests first**

Update `tests/test_major_project_workflows.py` to require allocator steps before phase calls:

- `AllocateBigDesignVisit` before `RunBigDesignPhase`
- `AllocatePlanVisit` before `RunPlanPhase`
- `AllocateImplementationVisit` before `RunImplementationPhase`

Also assert that reusable phase calls bind `state_root` from allocator artifacts, not directly from `inputs.*_phase_state_root`.

- [ ] **Step 2: Add output-read tests**

Add tests that search the stack YAML and fail if route gates still read final phase outputs from the base inputs:

- `${inputs.big_design_phase_state_root}/final_design_review_decision.txt`
- `${inputs.plan_phase_state_root}/final_plan_review_decision.txt`
- `${inputs.implementation_phase_state_root}/final_implementation_review_decision.txt`

The replacement should read from active allocated roots exposed by allocator bundles.

- [ ] **Step 3: Initialize the phase visit ledger**

In `InitializeItemState`, call:

```bash
python workflows/library/scripts/major_project_phase_visits.py init \
  --item-state-root "${inputs.item_state_root}" \
  --output-bundle "${inputs.item_state_root}/phase_visit_init_output.json"
```

Keep existing escalation context initialization.

- [ ] **Step 4: Allocate the first big-design visit**

Insert `AllocateBigDesignVisit` after initialization and before `RunBigDesignPhase`.

Use:

- phase: `big_design`
- base: `${inputs.big_design_phase_state_root}`
- allocation key: `initial-big-design`
- reason: `initial_big_design`

Bind `RunBigDesignPhase.with.state_root` to `steps.AllocateBigDesignVisit.artifacts.phase_state_root`.

- [ ] **Step 5: Read big-design outputs from the active visit root**

Change design approval and roadmap escalation gates to read `final_design_review_decision.txt` from the allocated big-design visit root.

Change `FinalizeEscalateRoadmapRevision` dependencies and reads for `final_roadmap_change_request_path.txt` to use the active big-design visit root.

- [ ] **Step 6: Allocate the first plan visit after design approval**

Route `ClearUpstreamAfterDesignApproval` to a new `AllocatePlanVisit` step instead of directly to `RunPlanPhase`.

Use:

- phase: `plan`
- base: `${inputs.plan_phase_state_root}`
- allocation key: `after-design-approval-plan`
- reason: `after_design_approval`

Bind `RunPlanPhase.with.state_root` to `steps.AllocatePlanVisit.artifacts.phase_state_root`.

- [ ] **Step 7: Read plan outputs from the active visit root**

Change plan approval and redesign gates to read `final_plan_review_decision.txt` from the allocated plan visit root.

Change `ActivatePlanEscalationContext` to read `final_plan_escalation_context_path.txt` from the allocated plan visit root.

- [ ] **Step 8: Allocate a redesign visit on `ESCALATE_REDESIGN`**

After `ActivatePlanEscalationContext`, route to `AllocateRedesignVisit`, then to `RunBigDesignPhase`.

Use:

- phase: `big_design`
- base: `${inputs.big_design_phase_state_root}`
- allocation key derived from the plan visit index, for example `plan-escalate-redesign-${steps.AllocatePlanVisit.artifacts.visit_index}`
- reason: `plan_escalate_redesign`
- source context path: `${inputs.upstream_escalation_context_path}`

Bind the next design call to the newly allocated big-design visit root.

- [ ] **Step 9: Allocate implementation visit after plan approval**

Route `ClearUpstreamAfterPlanApproval` to `AllocateImplementationVisit`, then to `RunImplementationPhase`.

Use:

- phase: `implementation`
- base: `${inputs.implementation_phase_state_root}`
- allocation key derived from the plan visit index, for example `after-plan-${steps.AllocatePlanVisit.artifacts.visit_index}-implementation`
- reason: `after_plan_approval`

Bind `RunImplementationPhase.with.state_root` to the allocated implementation visit root.

- [ ] **Step 10: Read implementation outputs from the active visit root**

Change implementation approval and replan gates to read `final_implementation_review_decision.txt` from the allocated implementation visit root.

Change `ActivateImplementationEscalationForReplan` to read `final_implementation_escalation_context_path.txt` from the allocated implementation visit root.

- [ ] **Step 11: Allocate a replan visit on `ESCALATE_REPLAN`**

After `ActivateImplementationEscalationForReplan`, route to `AllocateReplanVisit`, then to `RunPlanPhase`.

Use:

- phase: `plan`
- base: `${inputs.plan_phase_state_root}`
- allocation key derived from the implementation visit index, for example `implementation-escalate-replan-${steps.AllocateImplementationVisit.artifacts.visit_index}`
- reason: `implementation_escalate_replan`
- source context path: `${inputs.upstream_escalation_context_path}`

Keep `plan_target_path` stable so the approved replan replaces the authoritative plan artifact.

- [ ] **Step 12: Keep implementation iteration ledger semantics explicit**

Audit `reset-ledger-on-design-approval` and `terminal-cleanup` calls. If those operations must keep spanning implementation visits in one design epoch, keep their ledger under `${inputs.implementation_phase_state_root}`. If they are visit-local, move them to the allocated implementation visit root and update tests accordingly.

Default recommendation: keep the cumulative implementation iteration ledger under the implementation base root because the threshold is intentionally cumulative across implementation attempts since the last approved design.

- [ ] **Step 13: Run focused YAML shape tests**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration pytest tests/test_major_project_workflows.py -q -k "major_project or tranche_stack or escalation"
```

Expected: tests covering major-project workflow shape pass.

### Task 4: Wire the approved-design continuation stack

**Files:**
- Modify: `workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml`
- Modify: `tests/test_major_project_workflows.py`

- [ ] **Step 1: Add continuation shape tests**

Require:

- phase visit initialization
- `AllocatePlanVisit` before `RunPlanPhase`
- `AllocateImplementationVisit` before `RunImplementationPhase`
- `AllocateReplanVisit` after implementation `ESCALATE_REPLAN`

- [ ] **Step 2: Add phase visit initialization**

In `InitializeItemState`, call the phase visit helper `init` command.

- [ ] **Step 3: Allocate plan visit before the first plan call**

Use:

- phase: `plan`
- base: `${inputs.plan_phase_state_root}`
- allocation key: `approved-design-initial-plan`
- reason: `approved_design_initial_plan`

- [ ] **Step 4: Allocate implementation visit after plan approval**

Use an allocation key derived from the active plan visit index.

- [ ] **Step 5: Allocate replan visit after implementation escalation**

Route `ActivateImplementationEscalationForReplan` to `AllocateReplanVisit`, then to `RunPlanPhase`.

- [ ] **Step 6: Update all output reads**

All checks and escalation context reads must use allocated active roots, not base inputs.

- [ ] **Step 7: Run focused continuation tests**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration pytest tests/test_major_project_workflows.py -q -k "approved_design or continue_from_approved_design or replan"
```

Expected: continuation stack tests pass.

### Task 5: Add runtime regression coverage for the original crash

**Files:**
- Modify: `tests/test_major_project_workflows.py`
- Modify if better isolated: `tests/test_workflow_examples_v0.py`

- [ ] **Step 1: Build a mocked provider scenario**

Create or adapt a runtime test that runs the selected-tranche stack with mocked phase providers:

1. First plan visit approves.
2. First implementation visit emits `ESCALATE_REPLAN`.
3. Second plan visit approves.
4. Second implementation visit approves.

- [ ] **Step 2: Assert no write-root collision**

Expected assertions:

- workflow status is `succeeded`
- no step error has reason `colliding_write_root_binding`
- first and second plan call frames have different bound `state_root` values
- item outcome is `APPROVED`

- [ ] **Step 3: Add redesign regression**

Add the same style of test for:

1. First plan visit emits `ESCALATE_REDESIGN`.
2. Second big-design visit approves.
3. Next plan and implementation approve.

Expected: big-design call roots differ.

- [ ] **Step 4: Run the runtime regression tests**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration pytest tests/test_major_project_workflows.py -q -k "replan or redesign or write_root"
```

Expected: re-entry scenarios pass without `colliding_write_root_binding`.

### Task 6: Update docs and examples

**Files:**
- Modify if needed: `workflows/README.md`
- Modify if needed: `docs/index.md`

- [ ] **Step 1: Update workflow catalog wording**

If the catalog describes the selected-tranche stack, mention that upward re-entry allocates phase visit roots below the phase base roots.

- [ ] **Step 2: Index the new plan if docs index convention requires it**

Add this plan to `docs/index.md` only if the current index is still the authoritative plan catalog and the worktree owner has not made conflicting changes.

- [ ] **Step 3: Avoid prompt-literal tests**

Do not add tests that assert literal prompt phrasing. Use workflow shape, contract, artifact lineage, and runtime behavior assertions.

### Task 7: Verification

**Files:**
- No new implementation files beyond previous tasks.

- [ ] **Step 1: Run new test collection**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration pytest --collect-only tests/test_major_project_phase_visits.py tests/test_major_project_workflows.py
```

Expected: collection succeeds.

- [ ] **Step 2: Run focused unit and workflow tests**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration pytest tests/test_major_project_phase_visits.py tests/test_major_project_workflows.py -q -k "phase_visit or major_project or tranche_stack or replan or redesign or write_root"
```

Expected: all selected tests pass.

- [ ] **Step 3: Run reusable-call collision tests**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration pytest tests/test_subworkflow_calls.py -q -k "write_root"
```

Expected: existing collision guard tests still pass.

- [ ] **Step 4: Run an orchestrator dry-run smoke**

Use a major-project drain or continuation example with explicit fixture inputs as needed:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml --dry-run
```

If the example requires typed inputs, supply existing fixture paths or add a minimal fixture in the test suite instead of weakening validation.

- [ ] **Step 5: Run an EasySpin smoke only after syncing downstream**

If the workflow fix is copied into the EasySpin checkout, run EasySpin workflow smoke commands in the `ptycho311` environment. For long-running live workflow commands, use the `tmux` skill. Prefer:

```bash
source /home/ollie/miniconda3/etc/profile.d/conda.sh
conda activate ptycho311
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator ...
```

Expected: the replan route reaches the next plan visit instead of failing with `colliding_write_root_binding`.

## Migration Notes

This fix changes future selected-tranche execution. A run that already recorded a failed call-frame collision may not be cleanly resumable from the exact failed call because the old run state already contains the earlier colliding call binding. For a failed EasySpin run, prefer one of these explicit recovery paths after the fix is available:

- resume only if the workflow checksum and call-frame state allow the allocator steps to run before the repeated phase call
- otherwise restart at the selected-tranche or drain-iteration boundary with a fresh selected-tranche state root

Do not relaunch the entire roadmap phase unless the roadmap approval state itself needs to be regenerated.

## Success Criteria

- Re-entering plan after `ESCALATE_REPLAN` binds a fresh plan visit root.
- Re-entering big design after `ESCALATE_REDESIGN` binds a fresh big-design visit root.
- Stable artifact target paths continue to represent the authoritative latest design, plan, execution report, review reports, and item summary.
- The reusable-call collision guard remains unchanged and still catches real aliasing.
- Existing escalation context behavior remains intact.
- Major-project workflow tests and at least one orchestrator smoke check pass.
