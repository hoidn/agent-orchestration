# Observability Step-Visit Summaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate one observability summary per executed provider/phase visit, including nested loop provider visits, without changing workflow semantics.

**Architecture:** Keep summaries advisory and run-local. Emit summaries from nested loop body persistence after normalized results are stored, and make summary filenames/index entries visit-scoped when runtime identity is present.

**Tech Stack:** Python runtime, existing orchestrator workflow executor, `SummaryObserver`, pytest.

---

### Task 1: Summary Observer Visit Identity

**Files:**
- Modify: `orchestrator/observability/summary.py`
- Test: `tests/test_observability_summary_modes.py`

- [x] **Step 1: Write failing tests**

Add tests that emit two provider summaries for the same step name with different
`step.output.step_id` or `step.output.visit_count` values. Assert both summary
files exist, both index entries exist, and paths are distinct.

- [x] **Step 2: Run red test**

Run:

```bash
python -m pytest tests/test_observability_summary_modes.py::test_summary_observer_uses_visit_identity_for_distinct_files -q
```

Expected: fail because both visits currently target the same summary path.

- [x] **Step 3: Implement visit-aware stems and index metadata**

Update `SummaryObserver.emit` so `_file_stem` receives the snapshot. If the
snapshot has a runtime `step_id`, append a safe identity suffix and optional
`visit-<n>`. Add `step_id` and `visit_count` to index entries when present.

- [x] **Step 4: Verify task tests**

Run:

```bash
python -m pytest tests/test_observability_summary_modes.py -q
```

Expected: pass.

### Task 2: Nested Loop Summary Emission

**Files:**
- Modify: `orchestrator/workflow/executor.py`
- Test: `tests/test_observability_summary_runtime.py`

- [x] **Step 1: Write failing runtime test**

Add a workflow with a `repeat_until` body containing a provider step that runs
two iterations before approval. Enable `phase-performance` summaries and use a
fake summary provider. Assert the run completes, the aggregate summary index has
two provider entries for the nested provider, and their summary paths differ.

- [x] **Step 2: Run red test**

Run:

```bash
python -m pytest tests/test_observability_summary_runtime.py::test_phase_performance_profile_summarizes_nested_provider_visits -q
```

Expected: fail because nested provider body steps do not emit summaries.

- [x] **Step 3: Emit summaries after nested loop persistence**

In `_execute_nested_loop_step`, call `_emit_step_summary` after the finalized
result is stored and consumes are finalized. Use the nested display name and
the finalized result, which includes `step_id`.

- [x] **Step 4: Verify runtime tests**

Run:

```bash
python -m pytest tests/test_observability_summary_runtime.py -q
```

Expected: pass.

### Task 3: Documentation Alignment

**Files:**
- Modify: `docs/design/dashboard_observability_summary_gui.md`
- Modify: `docs/design/observability_step_visit_summaries.md`

- [x] **Step 1: Update dashboard design**

Document that summary entries are visit records and may have multiple entries
for the same logical provider step.

- [x] **Step 2: Run focused verification**

Run:

```bash
python -m pytest tests/test_observability_summary_modes.py tests/test_observability_summary_runtime.py tests/test_dashboard_server.py -q
```

Expected: pass.
