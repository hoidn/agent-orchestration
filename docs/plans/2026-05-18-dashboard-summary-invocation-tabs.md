# Dashboard Summary Invocation Tabs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Summary Hub step cards show all invocations of a repeated step as selectable panels, with summary and input/output links resolved from the same invocation state.

**Architecture:** Group summary entries by invocation identity (`frame_root`, `step_id`, or summary path) and render native collapsed `<details>` panels under each step card. Resolve each panel's input/output links through the exact call-frame state associated with that summary entry before falling back to the current detail state. Treat each panel as a self-contained invocation lineage, so child summaries and enclosing call/repeat context do not mix links from different visits.

**Tech Stack:** Python stdlib dashboard HTML renderer, JSON run state, pytest.

---

### Task 1: Invocation Grouping Tests

**Files:**
- Modify: `tests/test_dashboard_server.py`

- [x] **Step 1: Write failing test for multiple invocation panels**

Add a dashboard test with one authored provider step and two summary index
entries with distinct `frame_root` values. Assert both "Invocation 1" and
"Invocation 2" appear and both summary links are visible.

- [x] **Step 2: Run red test**

Run:

```bash
python -m pytest tests/test_dashboard_server.py::test_summary_hub_groups_repeated_step_summaries_by_invocation -q
```

Expected: fail because current rendering uses one flat summary artifact list.

### Task 2: Frame-Scoped Output Links

**Files:**
- Modify: `tests/test_dashboard_server.py`
- Modify: `orchestrator/dashboard/server.py`

- [x] **Step 1: Write failing frame-scope test**

Create a parent run state with two call frames for the same called workflow.
Each frame has different `bound_inputs.state_root`, expected-output pointer
contents, and target Markdown file. Add two summary entries for the same step,
one per frame. Assert Invocation 1 links only the first target and Invocation 2
links only the second target.

- [x] **Step 2: Run red test**

Run:

```bash
python -m pytest tests/test_dashboard_server.py::test_summary_hub_invocation_links_use_matching_call_frame_state -q
```

Expected: fail because output links are currently resolved from a single latest
called-workflow state.

- [x] **Step 3: Implement invocation grouping**

Add helpers in `orchestrator/dashboard/server.py` to group summary entries,
derive invocation labels, and render one collapsed invocation panel per group.

- [x] **Step 4: Implement frame-root state lookup**

Convert summary `frame_root` path segments such as
`call_frames/root.loop#0.step__visit__1` back to state call-frame ids such as
`root.loop#0.step::visit::1`, then walk nested `state.call_frames` maps.

- [x] **Step 5: Resolve links per invocation**

For each invocation panel, build input/output/publish/consume links with the
frame-scoped detail when available. Keep the panel self-contained: summary links
and authored file links must come from the same invocation lineage.

- [x] **Step 6: Verify dashboard tests**

Run:

```bash
python -m pytest tests/test_dashboard_server.py -q
```

Expected: pass.

### Task 3: Documentation and Focused Verification

**Files:**
- Modify: `docs/design/dashboard_observability_summary_gui.md`
- Modify: `docs/design/dashboard_summary_invocation_tabs.md`
- Modify: `docs/plans/2026-05-18-dashboard-summary-invocation-tabs.md`

- [x] **Step 1: Update dashboard design docs**

Document invocation panels and frame-scoped link resolution.

- [x] **Step 2: Run focused verification**

Run:

```bash
python -m pytest tests/test_dashboard_server.py tests/test_observability_summary_modes.py tests/test_observability_summary_runtime.py -q
python -m pytest --collect-only tests/test_dashboard_server.py -q
git diff --check -- orchestrator/dashboard/server.py tests/test_dashboard_server.py docs/design/dashboard_observability_summary_gui.md docs/design/dashboard_summary_invocation_tabs.md docs/plans/2026-05-18-dashboard-summary-invocation-tabs.md
```

Expected: all commands pass.
