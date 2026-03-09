# Design-Plan-Implementation Stack Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a new call-based workflow stack example that runs a tracked design/ADR loop, then a tracked plan loop, then an implementation review/fix loop, while leaving the existing examples in place.

**Architecture:** Build a small top-level `2.7` parent workflow that delegates to three reusable library workflows: a tracked design phase, a tracked plan phase, and an implementation phase. Reuse the repo's structured `match` / `repeat_until` / `call` patterns, publish stable outputs from each phase, and keep the stack example concrete with a sample feature brief input.

**Tech Stack:** Workflow DSL `2.7`, Codex provider examples, example prompt files, pytest workflow smoke tests, orchestrator dry-run validation.

---

### Task 1: Add failing example-workflow coverage for the new stack

**Files:**
- Modify: `tests/test_workflow_examples_v0.py`

**Step 1: Add the new example and library workflow names to the test module**

Update `EXAMPLE_FILES` and add a new runtime smoke test skeleton for the stack:
- `workflows/examples/design_plan_impl_review_stack_v2_call.yaml`
- `workflows/library/tracked_design_phase.yaml`
- `workflows/library/tracked_plan_phase.yaml`
- `workflows/library/design_plan_impl_implementation_phase.yaml`

**Step 2: Write the failing runtime smoke test**

Model it after the existing modular call-based follow-on workflow smoke test:
- copy the new example, library workflows, prompt files, and sample brief into a temp workspace
- initialize bound inputs
- patch `ProviderExecutor.prepare_invocation` / `execute`
- drive provider calls through:
  - draft design
  - review design (`REVISE`, then `APPROVE`)
  - revise design
  - draft plan
  - review plan (`REVISE`, then `APPROVE`)
  - revise plan
  - execute implementation
  - review implementation (`REVISE`, then `APPROVE`)
  - fix implementation
- assert final workflow outputs and `call_frames` shape

**Step 3: Run the new test to verify it fails**

Run:

```bash
pytest tests/test_workflow_examples_v0.py::test_design_plan_impl_review_stack_v2_call_runtime -v
```

Expected: FAIL because the workflow files do not exist yet.

### Task 2: Add the tracked design-phase library and prompts

**Files:**
- Create: `workflows/library/tracked_design_phase.yaml`
- Create: `prompts/workflows/design_plan_impl_stack_v2_call/draft_design.md`
- Create: `prompts/workflows/design_plan_impl_stack_v2_call/review_design.md`
- Create: `prompts/workflows/design_plan_impl_stack_v2_call/revise_design.md`

**Step 1: Create the tracked design-phase library**

Build a `2.7` library workflow that:
- accepts `state_root`, `brief_path`, `design_target_path`, and `design_review_report_target_path`
- seeds an empty open-findings ledger under `state_root`
- drafts the ADR/design
- runs a tracked `repeat_until` design loop
- supports review decisions `APPROVE`, `REVISE`, and `BLOCK`
- fails immediately on `BLOCK`
- exports final `design_path`, `design_review_report_path`, and `design_review_decision`

**Step 2: Create design prompts**

Keep the prompts simple and task-facing:
- `draft_design.md`: draft the design/ADR from the consumed brief
- `review_design.md`: perform a hard-nosed tracked review, allow refactoring/debt findings when they are prerequisites, write JSON plus decision/count files
- `revise_design.md`: address unresolved findings and update the design in place

**Step 3: Do not add production behavior outside the new library**

Keep the design phase self-contained. Do not modify existing workflows or libraries in this task.

### Task 3: Add the tracked plan-phase library and prompts

**Files:**
- Create: `workflows/library/tracked_plan_phase.yaml`
- Create: `prompts/workflows/design_plan_impl_stack_v2_call/draft_plan.md`
- Create: `prompts/workflows/design_plan_impl_stack_v2_call/review_plan.md`
- Create: `prompts/workflows/design_plan_impl_stack_v2_call/revise_plan.md`

**Step 1: Create the tracked plan-phase library**

Build a `2.7` library workflow that:
- accepts `state_root`, `design_path`, `plan_target_path`, and `plan_review_report_target_path`
- seeds an empty open-findings ledger under `state_root`
- drafts a plan from the approved design
- runs a tracked `repeat_until` plan loop with `APPROVE|REVISE`
- exports final `plan_path`, `plan_review_report_path`, and `plan_review_decision`

**Step 2: Create plan prompts**

Reuse the tracked-findings contract shape:
- fresh review first
- reconcile against carried-forward findings
- write JSON review report plus decision/count files
- revise only unresolved/new findings

### Task 4: Add the implementation-phase library, top-level stack example, and sample brief

**Files:**
- Create: `workflows/library/design_plan_impl_implementation_phase.yaml`
- Create: `workflows/examples/design_plan_impl_review_stack_v2_call.yaml`
- Create: `workflows/examples/inputs/provider_session_resume_brief.md`
- Create: `prompts/workflows/design_plan_impl_stack_v2_call/implement_plan.md`
- Create: `prompts/workflows/design_plan_impl_stack_v2_call/review_implementation.md`
- Create: `prompts/workflows/design_plan_impl_stack_v2_call/fix_implementation.md`

**Step 1: Add the implementation-phase library**

Use the existing `follow_on_implementation_phase.yaml` shape as the model, but point it at the new prompt tree and keep the prompts generic to “design + plan + execution report”.

**Step 2: Add the top-level stack workflow**

Create a `2.7` parent workflow that:
- accepts a feature brief path
- calls `tracked_design_phase`
- calls `tracked_plan_phase`
- calls `design_plan_impl_implementation_phase`
- exports final design, plan, execution report, implementation review report, and implementation review decision

Use fixed `state_root` values per phase so the example stays deterministic.

**Step 3: Add a concrete sample brief**

Create a short feature brief for provider-session resume so the example can validate with defaults and the workflow has a realistic input.

### Task 5: Make the failing test pass and add catalog/docs updates

**Files:**
- Modify: `tests/test_workflow_examples_v0.py`
- Modify: `workflows/README.md`

**Step 1: Update the runtime smoke test assertions**

Assert:
- final workflow outputs are present
- the three call steps export the expected artifacts
- the design and plan loops iterate once through `REVISE` and then `APPROVE`
- the implementation phase iterates once through `REVISE` and then `APPROVE`
- three call frames are persisted

**Step 2: Update the workflow catalog**

Add:
- the new top-level example workflow
- the three new reusable library workflows

**Step 3: Run the focused tests and make them pass**

Run:

```bash
pytest tests/test_workflow_examples_v0.py::test_design_plan_impl_review_stack_v2_call_runtime -v
pytest tests/test_workflow_examples_v0.py::test_workflow_examples_v0_load -v
pytest --collect-only tests/test_workflow_examples_v0.py -q
```

Expected: PASS for the two runtime/load tests; collect-only should include the new test without import errors.

### Task 6: Run workflow validation smoke checks

**Files:**
- No code changes expected

**Step 1: Dry-run the new top-level workflow**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.yaml --dry-run --stream-output
```

Expected: validation successful with default input values.

**Step 2: Run diff checks**

Run:

```bash
git diff --check -- \
  workflows/examples/design_plan_impl_review_stack_v2_call.yaml \
  workflows/library/tracked_design_phase.yaml \
  workflows/library/tracked_plan_phase.yaml \
  workflows/library/design_plan_impl_implementation_phase.yaml \
  prompts/workflows/design_plan_impl_stack_v2_call \
  workflows/examples/inputs/provider_session_resume_brief.md \
  workflows/README.md \
  tests/test_workflow_examples_v0.py
```

Expected: no whitespace or conflict-marker issues.
