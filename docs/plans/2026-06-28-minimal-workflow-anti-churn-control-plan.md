# Minimal Workflow Anti-Churn Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees.

**Goal:** Prevent model-proposed prerequisite recovery routes and stale evidence conflicts from turning into repeated bookkeeping/design-gap churn.

**Architecture:** Keep prompts responsible for local judgment, but make workflow scripts responsible for deciding whether a proposed prerequisite dependency route may become durable state. Do not add new top-level workflow statuses; reuse existing blocked recovery, dependency-edge, and step-back mechanisms.

**Tech Stack:** Agent-orchestration DSL v2.14 YAML, provider prompts, Python command adapters under `workflows/library/scripts/`, and pytest.

---

## Scope

This is a minimal control fix, not a redesign of the drain.

In scope:

- Treat blocked-recovery classifier output as a proposed route.
- Prevent stale/duplicate prerequisite dependency routes from being recorded as durable recovery state.
- Make selector and classifier prompts reject bookkeeping-only work unless it directly unblocks semantic implementation.
- Extend existing tests for recovery dependency routing and non-progress detection.

Out of scope:

- Deterministic validation for `GAP_DESIGN_REVISION_REQUIRED` or `TARGET_DESIGN_REVISION_REQUIRED`; those routes remain review-loop governed in this minimal plan.
- New workflow statuses such as `RECONCILE_STATE` or `INVALID_SELECTED_SCOPE`.
- New target-design-specific examples or strings.
- Rewriting the design-delta drain architecture.
- Changing `.orc` migration semantics.
- Broad prompt rewrites.

## File Map

- Modify `workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md`
  - Add a short generic rule that missing/stale summaries, manifests, reports, labels, or evidence are not implementation work unless tied to an unmet target contract.
- Modify `workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md`
  - State that the classifier proposes a route and must not use prerequisite/design-revision routes for stale evidence or wrong selected scope.
- Modify `workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py`
  - Validate `PREREQUISITE_GAP_REQUIRED` dependency edges against current run state before recording them.
- Modify `workflows/library/scripts/evaluate_workflow_non_progress.py`
  - Preserve fail-fast stale/evidence-only step-back behavior; keep this task to tests unless existing code does not already do that.
- Modify `tests/test_lisp_frontend_autonomous_drain_runtime.py`
  - Add recorder subprocess tests for completed prerequisite and invalid duplicate prerequisite before durable recording.
- Modify `tests/test_workflow_non_progress_recovery.py`
  - Add a regression for stale/evidence-only recovery producing step-back.
- Modify `workflows/examples/lisp_frontend_design_delta_drain.yaml`
  - Only if needed to pass existing threshold parameters into `evaluate_workflow_non_progress.py`; prefer no YAML change if the current thresholds already cover the case.

## Preconditions

- [ ] **Step 1: Inspect dirty state**

Run:

```bash
git status --short
```

Expected:

- Identify any unrelated dirty files.
- Do not bundle unrelated current-run edits into this plan.
- If `workflows/examples/lisp_frontend_design_delta_drain.yaml` or `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml` already contain the `ClassifyBlockedImplementationRecovery` `gpt-5.5` provider override, either commit that as a separate model-routing change first or explicitly include it in this plan's final commit message.

- [ ] **Step 2: Re-read governing docs**

Run:

```bash
sed -n '1,180p' docs/workflow_drafting_guide.md
sed -n '1,220p' specs/providers.md
sed -n '1,180p' specs/dsl.md
```

Expected:

- Confirm the split: prompts propose local judgment; workflow scripts validate, route, and record durable state.

## Task 1: Prompt Guardrails

**Files:**

- Modify: `workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md`
- Modify: `workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md`

- [ ] **Step 1: Add selector guardrail**

Add a concise generic rule near the selector decision rules:

```text
Do not select or draft work whose only purpose is to align summaries, manifests,
reports, labels, or stale evidence. Select or draft work only when it advances
an unmet target-design contract or directly unblocks semantic implementation.
```

- [ ] **Step 2: Add classifier guardrail**

Add a concise generic rule after the route descriptions:

```text
Treat this classification as a proposed recovery route. Do not choose
PREREQUISITE_GAP_REQUIRED, TARGET_DESIGN_REVISION_REQUIRED, or
GAP_DESIGN_REVISION_REQUIRED for stale evidence, duplicate bookkeeping, or a
selected unit whose scope should be replaced from the higher-level contract.
```

- [ ] **Step 3: Check prompt diffs**

Run:

```bash
git diff -- workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md
```

Expected:

- Two small generic edits.
- No project-specific examples.
- No long negative list.

## Task 2: Deterministic Prerequisite Route Validation

**Files:**

- Modify: `workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Write failing tests**

Add focused recorder subprocess tests using temporary run-state and recovery bundles. Put them next to the existing `record_lisp_frontend_blocked_recovery_outcome.py` subprocess tests, not in the pure dependency-graph helper test module:

```python
def test_blocked_recovery_recorder_does_not_persist_completed_prerequisite(...):
    ...
    # recovery bundle proposes PREREQUISITE_GAP_REQUIRED for blocker "context"
    # run state already lists completed_design_gaps ["context"]
    ...
    assert original_entry["recovery_status"] == "RETRY_READY"
    assert original_entry["prerequisite_recovery_status"] == "COMPLETED"
    assert original_entry["recovery_dependency_edge"]["status"] == "ready_to_retry"
    assert state["history"][-1]["event"] == "prerequisite_recovery_satisfied"
    assert summary["record_status"] == "RETRY_READY"
```

```python
def test_blocked_recovery_recorder_rejects_duplicate_prerequisite_edge(...):
    ...
    # recovery bundle proposes original gap as its own requires_completion blocker
    ...
    assert result.returncode != 0
    assert "Invalid recovery_dependency_edge" in result.stderr
```

Use existing helper patterns from the nearby runtime tests and from `record_lisp_frontend_prerequisite_recovery_outcome.py` coverage.

- [ ] **Step 2: Run failing tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "blocked_recovery_recorder" -q
```

Expected:

- New tests fail before implementation, or collect successfully and fail with the expected assertion.

- [ ] **Step 3: Implement validation**

In `record_lisp_frontend_blocked_recovery_outcome.py`:

- after `_dependency_edge_from_bundle(...)` returns the normalized edge JSON;
- load the current run state from `args.state_path`;
- reconstruct the normalized edge;
- call `evaluate_edge(edge, state)`;
- if the decision is `RETRY_TARGET`, update the original blocked entry directly:
  - `recovery_status = "RETRY_READY"`;
  - `prerequisite_recovery_status = "COMPLETED"`;
  - `recovery_dependency_edge.status = "ready_to_retry"`;
  - append a `prerequisite_recovery_satisfied` history event;
  - write a summary with `record_status = "RETRY_READY"`;
  - write drain status `CONTINUE`;
- if the decision is `INVALID_EDGE`, fail closed with a clear `SystemExit`;
- otherwise preserve current behavior for `SELECT_BLOCKER`, `BLOCKED_RECOVERABLE`, and `BLOCKED_TERMINAL`.

Keep this validation generic over `DESIGN_GAP` and `BACKLOG_ITEM`; do not mention Design Delta.
Prefer extracting or reusing the existing mutation shape from `record_lisp_frontend_prerequisite_recovery_outcome.py` rather than creating a new update command.

- [ ] **Step 4: Run route tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "blocked_recovery_recorder or prerequisite_recovery" -q
```

Expected:

- All recovery dependency tests pass.

## Task 3: Bookkeeping-Churn Step-Back Coverage

**Files:**

- Modify if needed: `workflows/library/scripts/evaluate_workflow_non_progress.py`
- Test: `tests/test_workflow_non_progress_recovery.py`

- [ ] **Step 1: Add regression test**

Add one generic test preserving the existing fail-fast behavior for bookkeeping/evidence-only stale artifact events.

Use existing event fields if possible. Prefer existing signals:

```python
_event(iteration=1, stale_artifact_detected=True, accepted_change=False)
```

Expected decision:

```python
assert decision["route"] == "STEP_BACK_REQUIRED"
assert "stale_artifact_provenance" in decision["trigger_codes"]
```

If existing stale-artifact logic already covers this, keep the test as documentation and do not change production code.
Do not weaken stale-artifact handling from fail-fast to repeated-event-only.

- [ ] **Step 2: Run non-progress tests**

Run:

```bash
python -m pytest tests/test_workflow_non_progress_recovery.py -q
```

Expected:

- Tests pass.

- [ ] **Step 3: Avoid YAML churn unless necessary**

Only edit `workflows/examples/lisp_frontend_design_delta_drain.yaml` if the test shows thresholds are not wired. If the existing thresholds already trigger step-back, do not touch YAML for this task.

## Task 4: Workflow Validation

**Files:**

- Validate: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Validate: `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml`

- [ ] **Step 1: Parse edited YAML and prompts**

Run:

```bash
python - <<'PY'
import yaml
from pathlib import Path
for p in [
    'workflows/examples/lisp_frontend_design_delta_drain.yaml',
    'workflows/library/lisp_frontend_design_delta_work_item.v214.yaml',
]:
    yaml.safe_load(Path(p).read_text())
    print('ok', p)
PY
```

Expected:

- Both files parse.

- [ ] **Step 2: Dry-run the target workflow**

Run:

```bash
python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml \
  --dry-run \
  --input target_design_path=docs/design/workflow_lisp_runtime_native_drain_authoring.md \
  --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md \
  --input steering_path=docs/steering.md \
  --input post_wcc_inventory_path=docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/post_wcc_current_state_inventory.json \
  --input progress_ledger_path=state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/progress_ledger.json \
  --input drain_state_root=state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain \
  --input run_state_target_path=state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain/run_state.json \
  --input drain_summary_target_path=artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain-summary.json \
  --input artifact_work_root=artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN \
  --input artifact_checks_root=artifacts/checks/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN \
  --input artifact_review_root=artifacts/review/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN \
  --input architecture_index_root=docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps
```

Expected:

- Workflow validation successful.
- Existing lint warnings are acceptable only if unchanged and unrelated.

## Task 5: Commit

- [ ] **Step 1: Review changed files**

Run:

```bash
git status --short
git diff --check
git diff -- workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md \
  workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md \
  workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py \
  workflows/library/scripts/evaluate_workflow_non_progress.py \
  tests/test_lisp_frontend_autonomous_drain_runtime.py \
  tests/test_workflow_non_progress_recovery.py \
  workflows/examples/lisp_frontend_design_delta_drain.yaml \
  workflows/library/lisp_frontend_design_delta_work_item.v214.yaml
```

Expected:

- No whitespace errors.
- No unrelated doc/target-design edits.
- If the earlier `gpt-5.5` classifier model change is still dirty, include it only if this commit is explicitly named as a classifier-control update.

- [ ] **Step 2: Commit**

Run:

```bash
git add workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md \
  workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md \
  workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py \
  workflows/library/scripts/evaluate_workflow_non_progress.py \
  tests/test_lisp_frontend_autonomous_drain_runtime.py \
  tests/test_workflow_non_progress_recovery.py \
  workflows/examples/lisp_frontend_design_delta_drain.yaml \
  workflows/library/lisp_frontend_design_delta_work_item.v214.yaml
git commit -m "Constrain workflow recovery churn"
```

If `evaluate_workflow_non_progress.py` or YAML files did not change, omit them from `git add`.

## Success Criteria

- Provider recovery classifications remain possible, but prerequisite dependency routes are not persisted when deterministic state proves them stale, duplicate, or invalid.
- Design-revision recovery routes remain bounded by prompt/review guardrails in this minimal plan; they are not claimed as deterministically validated here.
- Selector and classifier prompts remain general and concise.
- Existing step-back machinery handles stale/evidence-only churn without adding new workflow statuses or weakening fail-fast stale-artifact detection.
- Tests cover the observed failure class without naming this project-specific target design.
- The design-delta drain dry-run still validates.
