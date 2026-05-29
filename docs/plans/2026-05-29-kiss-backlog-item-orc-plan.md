# KISS Backlog Item ORC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal Workflow Lisp `.orc` example that processes one backlog item through typed planning and implementation phases.

**Architecture:** The example is a single-item subworkflow, not a full queue drain. It uses `provider-result` for provider-authored plan/implementation results, `review-revise-loop` for bounded review/fix behavior, typed records for phase surfaces, and frontend lowering to the existing v2.14 substrate. It is compile/lowering coverage only; shared-validation/runtime replacement remains future work for this shape.

**Tech Stack:** Workflow Lisp `.orc`, existing `orchestrator.workflow_lisp` compiler, pytest compile checks, existing generic design/plan/implementation prompt assets.

---

### Task 1: Add Compile Coverage

**Files:**
- Create: `tests/test_workflow_lisp_examples.py`
- Create later: `workflows/examples/kiss_backlog_item.orc`

- [ ] **Step 1: Write the failing test**
  Add a test that compiles `workflows/examples/kiss_backlog_item.orc` with explicit provider and prompt externs, then asserts the lowered workflows include the top-level item workflow plus the plan and implementation helper workflows.

- [ ] **Step 2: Verify the test fails**
  Run: `pytest --collect-only tests/test_workflow_lisp_examples.py -q`
  Run: `pytest tests/test_workflow_lisp_examples.py::test_kiss_backlog_item_orc_compiles_to_typed_phase_stack -q`
  Expected: the test is collected and then fails because the `.orc` file does not exist yet.

### Task 2: Add The `.orc` Example

**Files:**
- Create: `workflows/examples/kiss_backlog_item.orc`

- [ ] **Step 1: Define the types**
  Add path, context, phase input/result, review result, implementation attempt, and final item result types.

- [ ] **Step 2: Define the plan workflows**
  Use `provider-result` to draft a typed plan surface and a separate `with-phase` + `review-revise-loop` workflow to review it.

- [ ] **Step 3: Define the implementation workflows**
  Use `provider-result` to execute a typed implementation surface and a separate `with-phase` + `review-revise-loop` workflow to review it.

- [ ] **Step 4: Define the single-item entry workflow**
  Call the plan, plan-review, implementation, and implementation-review helpers and return a structured summary path.

- [ ] **Step 5: Verify compile test passes**
  Run: `pytest tests/test_workflow_lisp_examples.py::test_kiss_backlog_item_orc_compiles_to_typed_phase_stack -q`

### Task 3: Make The Example Discoverable

**Files:**
- Modify: `workflows/README.md`
- Modify: `docs/lisp_workflow_drafting_guide.md`

- [ ] **Step 1: Add catalog entry**
  Add `workflows/examples/kiss_backlog_item.orc` to the workflow catalog as a compile-checked Workflow Lisp example.

- [ ] **Step 2: Add drafting-guide note**
  Point authors who want a smaller starting point than a drain to the single-item `.orc` example.

- [ ] **Step 3: Run checks**
  Run the narrow pytest selector. A CLI shared-validation compile is intentionally out of scope until this helper-workflow review-loop shape has shared-validation/runtime parity.
