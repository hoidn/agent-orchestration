# NeurIPS Terminal Implementation State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove `RUNNING` / `WAITING` as normal NeurIPS backlog-drain states so long-running jobs remain under implementation-worker ownership until `COMPLETED` or `BLOCKED`.

**Architecture:** The implementation phase becomes terminal-only: `COMPLETED` for verified done work, `BLOCKED` for genuine blockers or documented failed recovery. The selected-item and drain wrappers stop exposing `WAITING`; long-running commands are treated as ordinary implementation work that must be monitored, recovered, and finished before returning.

**Long-run policy:** A provider may run a command in the foreground or launch it in tmux and poll it, but it must not return while ordinary training, benchmarking, or data generation is still running. Provider timeout behavior is workflow/runtime policy, not an agent-facing instruction to split scope or decide backlog state.

**Migration note:** Existing NeurIPS runs or run-state files that already contain `RUNNING` / `WAITING` values are pre-change state. Complete, block, or restart those runs before resuming under this terminal-state contract.

**Tech Stack:** Agent-orchestration YAML workflows, bundled workflow prompts, Python helper tests with `pytest`, orchestrator dry-run validation.

---

## File Structure

- Modify `workflows/library/neurips_backlog_implementation_phase.yaml`
  - Remove `RUNNING` from implementation-state contracts and finalization.
  - Delete the `PublishProgressReport` branch that only exists for `RUNNING`.
  - Keep blocked progress reports for `BLOCKED`.
  - Raise long implementation/fix provider timeouts to reduce runtime-level interruption of worker-owned runs.

- Modify `workflows/library/neurips_selected_backlog_item.yaml`
  - Remove `WAITING` from selected-item `drain_status` contracts.
  - Delete `RecordImplementationWaiting`.
  - Keep `CONTINUE` and `BLOCKED` terminal routing.

- Modify `workflows/examples/neurips_steered_backlog_drain.yaml`
  - Remove `WAITING` from top-level drain status contracts and iteration outputs.
  - Ensure repeat termination remains `DONE` or `BLOCKED`; `CONTINUE` continues.

- Modify `workflows/library/prompts/neurips_backlog_implementation_phase/implement_implementation.md`
  - Replace the state guidance with concise terminal-state guidance.
  - Require the implementer to keep ownership of long-running commands until exit, recover nonzero exits in scope, and only emit `COMPLETED` or `BLOCKED`.

- Modify `workflows/library/prompts/neurips_backlog_seeded_plan_phase/draft_plan.md`
  - Add one concise rule that plans must not use `RUNNING` as normal launch-and-stop behavior.

- Modify `workflows/library/prompts/neurips_backlog_seeded_plan_phase/review_plan.md`
  - Add one concise review rule rejecting plans that stop after launching ordinary long-running work.

- Modify `workflows/README.md`
  - Update the NeurIPS implementation phase description.
  - Record the compatibility rule for old `RUNNING` / `WAITING` run state.

- Modify or add tests in `tests/test_major_project_workflows.py` or a focused NeurIPS workflow test module.
  - Assert NeurIPS implementation-state contracts exclude `RUNNING`.
  - Assert NeurIPS drain contracts exclude `WAITING`.
  - Assert waiting-specific steps are removed.

## Task 1: Contract Tests

**Files:**
- Modify: `tests/test_major_project_workflows.py` or create a focused NeurIPS workflow contract test module.

- [ ] **Step 1: Write failing tests for terminal implementation state**

Add tests that load:

- `workflows/library/neurips_backlog_implementation_phase.yaml`
- `workflows/library/neurips_selected_backlog_item.yaml`
- `workflows/examples/neurips_steered_backlog_drain.yaml`

Assert:

```python
assert "RUNNING" not in implementation_state_allowed_values
assert "WAITING" not in selected_item_drain_status_allowed_values
assert "WAITING" not in top_level_drain_status_allowed_values
assert "PublishProgressReport" not in implementation_step_names
assert "RecordImplementationWaiting" not in selected_item_step_names
assert execute_implementation_timeout == 86400
assert fix_implementation_timeout == 86400
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
pytest -q tests/test_major_project_workflows.py -k 'neurips or terminal or waiting'
```

Expected: fails because current workflows still expose `RUNNING` / `WAITING`.

## Task 2: Implementation-Phase YAML

**Files:**
- Modify: `workflows/library/neurips_backlog_implementation_phase.yaml`

- [ ] **Step 1: Remove `RUNNING` from output and bundle contracts**

Change every NeurIPS implementation-state enum in this file from:

```yaml
allowed: ["COMPLETED", "RUNNING", "BLOCKED"]
```

to:

```yaml
allowed: ["COMPLETED", "BLOCKED"]
```

- [ ] **Step 2: Remove `RUNNING` validation in inline Python**

Change inline Python state validation sets from:

```python
{"COMPLETED", "RUNNING", "BLOCKED"}
```

to:

```python
{"COMPLETED", "BLOCKED"}
```

- [ ] **Step 3: Delete the `PublishProgressReport` step**

Remove the step named `PublishProgressReport`, because progress reports remain only for `BLOCKED`.

- [ ] **Step 4: Raise long implementation provider timeouts**

Increase `ExecuteImplementation` and `FixImplementation` from `timeout_sec: 43200` to `timeout_sec: 86400`.

- [ ] **Step 5: Simplify finalization**

In `FinalizeImplementationPhaseOutputs`, remove the `elif implementation_state == "RUNNING"` branch. Keep:

- `COMPLETED`: requires execution report, checks report, implementation review report, and review decision.
- `BLOCKED`: requires progress report and writes `NOT_APPLICABLE` review decision.

- [ ] **Step 6: Run focused YAML-contract test**

Run:

```bash
pytest -q tests/test_major_project_workflows.py -k 'neurips or terminal or waiting'
```

Expected: implementation-phase assertions pass; selected-item/drain assertions may still fail until later tasks.

## Task 3: Selected-Item YAML

**Files:**
- Modify: `workflows/library/neurips_selected_backlog_item.yaml`

- [ ] **Step 1: Remove `WAITING` from selected-item output contracts**

Change selected-item `drain_status` allowed values from:

```yaml
allowed: ["CONTINUE", "WAITING", "BLOCKED"]
```

to:

```yaml
allowed: ["CONTINUE", "BLOCKED"]
```

- [ ] **Step 2: Delete the waiting route**

Remove the step named `RecordImplementationWaiting` and any `RUNNING -> WAITING` routing logic.

- [ ] **Step 3: Update final selected-item validation**

Change inline validation from:

```python
if status not in {"CONTINUE", "WAITING", "BLOCKED"}:
```

to:

```python
if status not in {"CONTINUE", "BLOCKED"}:
```

- [ ] **Step 4: Run focused YAML-contract test**

Run:

```bash
pytest -q tests/test_major_project_workflows.py -k 'neurips or terminal or waiting'
```

Expected: selected-item assertions pass; top-level drain assertions may still fail until Task 4.

## Task 4: Top-Level Drain YAML

**Files:**
- Modify: `workflows/examples/neurips_steered_backlog_drain.yaml`

- [ ] **Step 1: Remove `WAITING` from top-level output and artifact contracts**

Change all top-level NeurIPS drain status allowed lists from:

```yaml
allowed: ["CONTINUE", "DONE", "WAITING", "BLOCKED"]
```

to:

```yaml
allowed: ["CONTINUE", "DONE", "BLOCKED"]
```

- [ ] **Step 2: Keep loop termination unchanged except for removed state**

The repeat loop should still terminate on:

- `DONE`
- `BLOCKED`

`CONTINUE` should still continue to the next iteration.

- [ ] **Step 3: Run focused YAML-contract test**

Run:

```bash
pytest -q tests/test_major_project_workflows.py -k 'neurips or terminal or waiting'
```

Expected: all terminal-state contract assertions pass.

## Task 5: Prompt Cleanup

**Files:**
- Modify: `workflows/library/prompts/neurips_backlog_implementation_phase/implement_implementation.md`
- Modify: `workflows/library/prompts/neurips_backlog_seeded_plan_phase/draft_plan.md`
- Modify: `workflows/library/prompts/neurips_backlog_seeded_plan_phase/review_plan.md`

- [ ] **Step 1: Replace implementation-state guidance**

In `implement_implementation.md`, replace the current state-guidance block with:

```text
Choose exactly one implementation state:
- `COMPLETED` when current-scope work is done, verified, and ready for review.
- `BLOCKED` only for a real blocker outside implementation authority, or after a documented failed recovery attempt.

If you launch a long-running command, keep ownership until it exits. On success, validate artifacts before `COMPLETED`. On failure, diagnose, fix in scope, and rerun or resume before choosing a final state.
```

Also update the JSON-output guidance:

```text
- always set `implementation_state`
- set `execution_report_path` only for `COMPLETED`
- set `progress_report_path` only for `BLOCKED`
- set `blocker_class` only for `BLOCKED`
```

Change the progress-report section title from `For RUNNING or BLOCKED` to `For BLOCKED`.

- [ ] **Step 2: Add concise plan-drafting rule**

In `draft_plan.md`, add:

```text
Plans must keep ordinary long-running commands under implementation ownership until terminal success or recoverable failure handling is complete.
```

- [ ] **Step 3: Add concise plan-review rule**

In `review_plan.md`, add:

```text
Reject plans that use a non-terminal state as the normal way to stop after launching training, benchmarks, or data generation.
```

- [ ] **Step 4: Update workflow docs**

In `workflows/README.md`, update the NeurIPS implementation phase entry so it no longer says the phase distinguishes `RUNNING`.

Add a short compatibility note that old `RUNNING` / `WAITING` NeurIPS run state should be completed, blocked, or restarted before resuming with the new contract.

- [ ] **Step 5: Run prompt/contract grep**

Run:

```bash
rg -n "RUNNING|WAITING" workflows/library/prompts/neurips_backlog_implementation_phase workflows/library/prompts/neurips_backlog_seeded_plan_phase workflows/library/neurips_backlog_implementation_phase.yaml workflows/library/neurips_selected_backlog_item.yaml workflows/examples/neurips_steered_backlog_drain.yaml
```

Expected: no hits for `RUNNING` or `WAITING` in the edited NeurIPS backlog-drain state surfaces.

## Task 6: Workflow Validation

**Files:**
- No new files unless tests require fixtures.

- [ ] **Step 1: Run focused tests**

Run:

```bash
pytest -q tests/test_major_project_workflows.py -k 'neurips or terminal or waiting'
```

Expected: pass.

- [ ] **Step 2: Run relevant existing tests**

Run:

```bash
pytest -q tests/test_major_project_workflows.py tests/test_neurips_backlog_roadmap_gate.py
```

Expected: pass.

- [ ] **Step 3: Run orchestrator dry-run for the NeurIPS drain**

Run from repo root:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml \
  --dry-run \
  --input steering_path=docs/fixtures/neurips/steering.md \
  --input design_path=docs/fixtures/neurips/design.md \
  --input roadmap_path=docs/fixtures/neurips/roadmap.md \
  --input roadmap_gate_path=docs/fixtures/neurips/roadmap_gate.json \
  --input progress_ledger_path=docs/fixtures/neurips/progress_ledger.json
```

If those fixture paths do not exist, use the existing NeurIPS dry-run fixture paths from the test suite or run the repository's current workflow validation command that covers `workflows/examples/neurips_steered_backlog_drain.yaml`.

Expected: dry-run validation succeeds. If fixture paths are absent, record the exact alternate validation command used.

## Task 7: Downstream Copy Check

**Files:**
- No direct edit in this repo unless downstream sync is part of the execution request.

- [ ] **Step 1: Check whether PtychoPINN carries copied workflow files**

Run:

```bash
for path in \
  workflows/library/neurips_backlog_implementation_phase.yaml \
  workflows/library/neurips_selected_backlog_item.yaml \
  workflows/examples/neurips_steered_backlog_drain.yaml \
  workflows/library/prompts/neurips_backlog_implementation_phase/implement_implementation.md \
  workflows/library/prompts/neurips_backlog_seeded_plan_phase/draft_plan.md \
  workflows/library/prompts/neurips_backlog_seeded_plan_phase/review_plan.md \
  workflows/README.md
do
  test -e "/home/ollie/Documents/PtychoPINN/$path" && echo "$path"
done
```

Expected: list copied downstream surfaces, if present.

- [ ] **Step 2: Copy edited surfaces to PtychoPINN when present**

Because PtychoPINN is the active NeurIPS backlog-drain consumer, copy edited workflow, prompt, and README surfaces to PtychoPINN when matching copied files exist.

- [ ] **Step 3: Validate downstream copied surfaces**

Run the same `rg -n "RUNNING|WAITING"` prompt/contract grep against the copied PtychoPINN surfaces and record any compatibility-only hits separately.

## Task 8: Commit

**Files:**
- Stage only the plan and implementation files touched by this work.

- [ ] **Step 1: Review diff**

Run:

```bash
git diff -- docs/plans/2026-04-29-neurips-terminal-implementation-state.md workflows/library/neurips_backlog_implementation_phase.yaml workflows/library/neurips_selected_backlog_item.yaml workflows/examples/neurips_steered_backlog_drain.yaml workflows/library/prompts/neurips_backlog_implementation_phase/implement_implementation.md workflows/library/prompts/neurips_backlog_seeded_plan_phase/draft_plan.md workflows/library/prompts/neurips_backlog_seeded_plan_phase/review_plan.md workflows/README.md tests/test_major_project_workflows.py tests/test_neurips_backlog_roadmap_gate.py
```

- [ ] **Step 2: Stage scoped files**

Run:

```bash
git add docs/plans/2026-04-29-neurips-terminal-implementation-state.md \
  workflows/library/neurips_backlog_implementation_phase.yaml \
  workflows/library/neurips_selected_backlog_item.yaml \
  workflows/examples/neurips_steered_backlog_drain.yaml \
  workflows/library/prompts/neurips_backlog_implementation_phase/implement_implementation.md \
  workflows/library/prompts/neurips_backlog_seeded_plan_phase/draft_plan.md \
  workflows/library/prompts/neurips_backlog_seeded_plan_phase/review_plan.md \
  workflows/README.md \
  tests/test_major_project_workflows.py
```

- [ ] **Step 3: Commit**

Run:

```bash
git commit -m "Remove non-terminal NeurIPS running state"
```
