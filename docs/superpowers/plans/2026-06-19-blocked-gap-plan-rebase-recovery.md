# Blocked Gap Plan Rebase Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit recovery branch so a revised blocked gap can require full execution-plan redraft, retirement, or ordinary retry instead of forcing incremental plan edits after the gap design or prerequisites made the old plan stale.

**Architecture:** Extend the blocked design revision report with a structured `plan_disposition`, route `PLAN_REBASE_REQUIRED` to a dedicated recovered-plan draft/review path, and make the recorder refuse `RUN_RECOVERED_GAP` until the redrafted plan has been approved. Keep provider judgment in prompts and deterministic routing/state updates in workflow YAML and scripts.

**Tech Stack:** Agent-orchestration DSL v2.14 YAML, provider `output_bundle`, command adapters, Python stdlib tests with `pytest`, workflow dry-run validation.

---

## File Structure

- Modify `workflows/examples/lisp_frontend_design_delta_drain.yaml`
  - Extend `ReviseBlockedDesignGap` output contract with `plan_disposition`.
  - Add plan-redraft preparation, provider draft, review, decision, and routing steps for recovered blocked gaps.
  - Gate recovered-gap retry on either `PLAN_STILL_VALID` or approved `PLAN_REBASE_REQUIRED`.

- Modify `workflows/library/prompts/lisp_frontend_design_delta_work_item/revise_prior_blocked_design_gap.md`
  - Require the design revision step to classify the existing plan as still valid, requiring rebase, retired, or blocked.
  - Define when each disposition applies.

- Create `workflows/library/prompts/lisp_frontend_design_delta_work_item/redraft_recovered_gap_plan.md`
  - Dedicated prompt for redrafting the execution plan from the revised gap design and current checkout evidence.

- Modify `workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py`
  - Read `plan_disposition`.
  - Record blocked recovery statuses for `PLAN_REBASE_REQUIRED` / `PLAN_RETIRED`.
  - Emit `RUN_RECOVERED_GAP` only when retry is allowed.

- Create or modify `workflows/library/scripts/write_lisp_frontend_recovered_plan_rebase_decision.py`
  - Normalize recovered-plan review outcome and plan disposition to `APPROVE`, `REVISE`, or `BLOCKED`.
  - If an equivalent helper already exists, extend that helper instead of creating this file.

- Modify tests in the narrowest existing module, likely `tests/test_loader_validation.py` or a new `tests/test_lisp_frontend_design_delta_recovery.py`
  - Add YAML validation and script behavior coverage for the new branch.
  - Do not assert literal prompt wording.

## Task 1: Extend The Revision Report Contract

**Files:**
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Modify: `workflows/library/prompts/lisp_frontend_design_delta_work_item/revise_prior_blocked_design_gap.md`

- [ ] **Step 1: Add a focused failing workflow-validation test**

Add a test that loads `workflows/examples/lisp_frontend_design_delta_drain.yaml` and asserts the `ReviseBlockedDesignGap` output bundle contains both `design_revision_decision` and `plan_disposition`.

Use a helper pattern already present in `tests/test_loader_validation.py`. If that module is too broad, create `tests/test_lisp_frontend_design_delta_recovery.py`.

Expected assertion shape:

```python
def test_blocked_design_revision_outputs_plan_disposition():
    workflow = load_workflow("workflows/examples/lisp_frontend_design_delta_drain.yaml")
    step = find_step(workflow, "ReviseBlockedDesignGap")
    fields = {field["name"]: field for field in step["output_bundle"]["fields"]}
    assert fields["design_revision_decision"]["allowed"] == ["REVISED", "BLOCKED"]
    assert fields["plan_disposition"]["allowed"] == [
        "PLAN_STILL_VALID",
        "PLAN_REBASE_REQUIRED",
        "PLAN_RETIRED",
        "BLOCKED",
    ]
```

Run: `python -m pytest tests/test_lisp_frontend_design_delta_recovery.py -k plan_disposition -q`

Expected: FAIL because `plan_disposition` is not declared.

- [ ] **Step 2: Extend the YAML output bundle**

In `ReviseBlockedDesignGap.output_bundle.fields`, add:

```yaml
              - name: plan_disposition
                json_pointer: /plan_disposition
                type: enum
                allowed:
                  - PLAN_STILL_VALID
                  - PLAN_REBASE_REQUIRED
                  - PLAN_RETIRED
                  - BLOCKED
              - name: stale_assumptions_count
                json_pointer: /stale_assumptions_count
                type: integer
```

Keep `stale_assumptions_count` optional only if the current output-bundle validator supports optional fields. If not, require the provider to write `0` for no stale assumptions.

- [ ] **Step 3: Update the prompt contract**

In `revise_prior_blocked_design_gap.md`, change the report shape to:

```json
{
  "design_revision_decision": "REVISED | BLOCKED",
  "plan_disposition": "PLAN_STILL_VALID | PLAN_REBASE_REQUIRED | PLAN_RETIRED | BLOCKED",
  "summary": "",
  "changed_sections": [],
  "blocker_class": "",
  "reason": "",
  "stale_assumptions_count": 0,
  "stale_assumptions": [],
  "required_baseline_commands": []
}
```

Add concise rules:

```text
Set `PLAN_REBASE_REQUIRED` when the revised gap design, target-design revision,
or completed prerequisite changes the execution plan's baseline, owned failure
surface, implementation route, or verification commands enough that local edits
would preserve stale assumptions.

Set `PLAN_RETIRED` when current evidence shows the blocked failure is already
resolved or superseded and the old plan should not be executed.

Set `PLAN_STILL_VALID` only when the existing plan remains executable after the
design revision and needs at most narrow consistency edits.
```

- [ ] **Step 4: Run the focused test**

Run: `python -m pytest tests/test_lisp_frontend_design_delta_recovery.py -k plan_disposition -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add workflows/examples/lisp_frontend_design_delta_drain.yaml \
        workflows/library/prompts/lisp_frontend_design_delta_work_item/revise_prior_blocked_design_gap.md \
        tests/test_lisp_frontend_design_delta_recovery.py
git commit -m "Add blocked gap plan disposition contract"
```

## Task 2: Teach The Recorder About Plan Disposition

**Files:**
- Modify: `workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py`
- Test: `tests/test_lisp_frontend_design_delta_recovery.py`

- [ ] **Step 1: Write failing unit tests for recorder behavior**

Add tests that invoke `record_lisp_frontend_blocked_recovery_outcome.py` with temporary state files and revision reports.

Cover these cases:

```python
@pytest.mark.parametrize("plan_disposition,expected_status", [
    ("PLAN_STILL_VALID", "RUN_RECOVERED_GAP"),
    ("PLAN_REBASE_REQUIRED", "CONTINUE"),
    ("PLAN_RETIRED", "CONTINUE"),
    ("BLOCKED", "BLOCKED"),
])
def test_gap_design_revision_plan_disposition_controls_retry(tmp_path, plan_disposition, expected_status):
    ...
```

Expected behavior:

- `PLAN_STILL_VALID`: existing behavior, record `gap_design_revision` and write `RUN_RECOVERED_GAP`.
- `PLAN_REBASE_REQUIRED`: record blocked/recovery state with `recovery_status=PLAN_REBASE_REQUIRED`, write `CONTINUE`, and do not run recovered gap yet.
- `PLAN_RETIRED`: record an event such as `blocked_recovery_plan_retired`, write `CONTINUE`, and do not run recovered gap.
- `BLOCKED`: fail closed as blocked.

Run: `python -m pytest tests/test_lisp_frontend_design_delta_recovery.py -k plan_disposition_controls_retry -q`

Expected: FAIL because the script ignores `plan_disposition`.

- [ ] **Step 2: Implement disposition parsing**

In the `GAP_DESIGN_REVISION_REQUIRED` branch, after loading `report`, add:

```python
plan_disposition = str(report.get("plan_disposition") or "PLAN_STILL_VALID").strip()
if plan_disposition not in {
    "PLAN_STILL_VALID",
    "PLAN_REBASE_REQUIRED",
    "PLAN_RETIRED",
    "BLOCKED",
}:
    raise SystemExit(f"Unexpected plan disposition: {plan_disposition}")
```

Then branch:

```python
if decision == "BLOCKED" or plan_disposition == "BLOCKED":
    return _run_update(args, "blocked", "gap_design_revision_blocked")

if plan_disposition == "PLAN_RETIRED":
    result = _run_update(
        args,
        "blocked",
        "gap_plan_retired",
        recovery_status="PLAN_RETIRED",
        prerequisite_gap_hint=str(report.get("summary") or "").strip(),
    )
    if result == 0 and args.terminal_action == "continue":
        Path(args.drain_status_path).write_text("CONTINUE\n", encoding="utf-8")
    return result

if plan_disposition == "PLAN_REBASE_REQUIRED":
    result = _run_update(
        args,
        "blocked",
        "gap_plan_rebase_required",
        recovery_status="PLAN_REBASE_REQUIRED",
        prerequisite_gap_hint=str(report.get("summary") or "").strip(),
    )
    if result == 0 and args.terminal_action == "continue":
        Path(args.drain_status_path).write_text("CONTINUE\n", encoding="utf-8")
    return result
```

Keep current `gap_design_revision` + `RUN_RECOVERED_GAP` behavior only for `PLAN_STILL_VALID`.

- [ ] **Step 3: Run recorder tests**

Run: `python -m pytest tests/test_lisp_frontend_design_delta_recovery.py -k plan_disposition_controls_retry -q`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py \
        tests/test_lisp_frontend_design_delta_recovery.py
git commit -m "Route blocked recovery by plan disposition"
```

## Task 3: Add The Recovered Plan Redraft Branch

**Files:**
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Create: `workflows/library/prompts/lisp_frontend_design_delta_work_item/redraft_recovered_gap_plan.md`
- Create or Modify: `workflows/library/scripts/write_lisp_frontend_recovered_plan_rebase_decision.py`
- Test: `tests/test_lisp_frontend_design_delta_recovery.py`

- [ ] **Step 1: Add failing YAML-structure tests**

Test that the workflow has these steps in order after `ReviseBlockedDesignGap` and before `RecordBlockedRecoveryOutcome` or before recovered retry:

- `PrepareRecoveredPlanReviewReportPath`
- `RedraftRecoveredGapPlan`
- `ReviewRedraftedRecoveredGapPlan`
- `WriteRecoveredPlanRebaseDecision`

Also assert the redraft step only runs when:

- `ClassifyBlockedImplementationRecovery.blocked_recovery_route == GAP_DESIGN_REVISION_REQUIRED`
- `ReviseBlockedDesignGap.design_revision_decision == REVISED`
- `ReviseBlockedDesignGap.plan_disposition == PLAN_REBASE_REQUIRED`

Run: `python -m pytest tests/test_lisp_frontend_design_delta_recovery.py -k recovered_plan_redraft_branch -q`

Expected: FAIL.

- [ ] **Step 2: Create the redraft prompt**

Create `redraft_recovered_gap_plan.md`:

```markdown
Redraft the execution plan for a recovered blocked design gap.

Read the consumed target design, baseline design, revised implementation
architecture, previous execution plan, blocked recovery bundle, design revision
report, and blocker progress report.

Write a fresh execution plan to the relpath recorded in the blocked recovery
bundle's `plan_path`. Do not preserve stale baseline claims, stale test
selectors, stale file maps, or stale status assumptions from the previous plan.

The plan must start from current checkout evidence. If the cited blocker is
already resolved or superseded, write a closure/status-refresh plan instead of
implementation steps.
```

Do not mention workflow loop mechanics in the prompt; keep it focused on the artifact the provider writes.

- [ ] **Step 3: Add preparation and redraft steps**

In `lisp_frontend_design_delta_drain.yaml`, add a report-path command:

```yaml
        - name: PrepareRecoveredPlanReviewReportPath
          id: prepare_recovered_plan_review_report_path
          when:
            all_of:
              - compare:
                  left:
                    ref: self.steps.ClassifyBlockedImplementationRecovery.artifacts.blocked_recovery_route
                  op: eq
                  right: GAP_DESIGN_REVISION_REQUIRED
              - compare:
                  left:
                    ref: self.steps.ReviseBlockedDesignGap.artifacts.design_revision_decision
                  op: eq
                  right: REVISED
              - compare:
                  left:
                    ref: self.steps.ReviseBlockedDesignGap.artifacts.plan_disposition
                  op: eq
                  right: PLAN_REBASE_REQUIRED
          command:
            - python
            - workflows/library/scripts/write_lisp_frontend_relpath_value.py
            - --value
            - ${inputs.artifact_review_root}/recovered-plan-redraft-iteration-${loop.index}-review.json
            - --under
            - artifacts/review
            - --output
            - ${inputs.drain_state_root}/iterations/${loop.index}/recovered-plan-review-target-path.txt
```

Then add `RedraftRecoveredGapPlan` using `provider: ${inputs.implementation_execute_provider}`, `input_file: workflows/library/prompts/lisp_frontend_design_delta_work_item/redraft_recovered_gap_plan.md`, and dependencies:

- target design
- baseline design
- blocked recovery bundle
- blocked recovery decision bundle
- blocked progress report
- blocked gap architecture
- blocked gap execution plan
- blocked design revision report

The provider should write to the existing plan path from the recovery bundle, not a new plan path.

- [ ] **Step 4: Add review and normalized decision**

Use the existing plan review prompt if possible:

```yaml
        - name: ReviewRedraftedRecoveredGapPlan
          provider: ${inputs.implementation_review_provider}
          input_file: workflows/library/prompts/lisp_frontend_design_delta_plan_phase/review_plan.md
```

Provide dependencies analogous to the normal `ReviewPlan`, but pointing at the recovered plan path and revised gap context.

Add `WriteRecoveredPlanRebaseDecision` as a command step. The helper should write one enum:

- `APPROVE`: redrafted plan approved.
- `REVISE`: redrafted plan needs another redraft/review iteration.
- `BLOCKED`: redraft impossible or plan retired.

For the first implementation, do not add an unbounded nested loop here. Prefer one redraft + one review. If review returns `REVISE`, record `TARGET_DESIGN_REVISION_REQUIRED` or `PLAN_REBASE_REQUIRED` and continue the outer drain. This keeps the recovery branch bounded and avoids another hidden plan-review loop.

- [ ] **Step 5: Gate recovered retry**

Update every `when.any_of` that currently allows recovered retry through `RecordBlockedRecoveryOutcome.artifacts.recovery_drain_status == RUN_RECOVERED_GAP`.

Add the condition that either:

- `ReviseBlockedDesignGap.plan_disposition == PLAN_STILL_VALID`, or
- `WriteRecoveredPlanRebaseDecision.recovered_plan_review_decision == APPROVE`.

Do not allow `RUN_RECOVERED_GAP` merely because the design was revised.

- [ ] **Step 6: Run YAML-structure tests**

Run: `python -m pytest tests/test_lisp_frontend_design_delta_recovery.py -k recovered_plan_redraft_branch -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add workflows/examples/lisp_frontend_design_delta_drain.yaml \
        workflows/library/prompts/lisp_frontend_design_delta_work_item/redraft_recovered_gap_plan.md \
        workflows/library/scripts/write_lisp_frontend_recovered_plan_rebase_decision.py \
        tests/test_lisp_frontend_design_delta_recovery.py
git commit -m "Add recovered gap plan redraft branch"
```

## Task 4: Persist Rebase/Retirement State Correctly

**Files:**
- Modify: `workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py`
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Test: `tests/test_lisp_frontend_design_delta_recovery.py`

- [ ] **Step 1: Add failing tests for run-state events**

Add tests for recorded history events:

- `PLAN_REBASE_REQUIRED` records `event=blocked`, `recovery_status=PLAN_REBASE_REQUIRED`, and includes `plan_path`.
- approved redraft records a distinct event, for example `gap_plan_rebase_approved`.
- `PLAN_RETIRED` records `recovery_status=PLAN_RETIRED` and does not set retry-ready.

Run: `python -m pytest tests/test_lisp_frontend_design_delta_recovery.py -k run_state_events -q`

Expected: FAIL until the recorder and workflow pass the right fields.

- [ ] **Step 2: Extend recorder state updates**

Add a small helper in `record_lisp_frontend_blocked_recovery_outcome.py`:

```python
def _append_plan_disposition_event(...):
    ...
```

Append structured history entries for:

- `blocked_recovery_plan_rebase_required`
- `blocked_recovery_plan_retired`
- `blocked_recovery_plan_rebase_approved`

Include:

- `item_id`
- `source`
- `plan_path`
- `architecture_path`
- `revision_report_path`
- `plan_disposition`
- `timestamp_utc`

- [ ] **Step 3: Wire approved redraft into recorder**

If `WriteRecoveredPlanRebaseDecision` writes `APPROVE`, call the recorder or a small helper to mark the plan rebase approved, then write `RUN_RECOVERED_GAP`.

Keep this deterministic; do not ask a provider to mutate run state.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_lisp_frontend_design_delta_recovery.py -k run_state_events -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py \
        workflows/examples/lisp_frontend_design_delta_drain.yaml \
        tests/test_lisp_frontend_design_delta_recovery.py
git commit -m "Record blocked plan rebase recovery state"
```

## Task 5: Add Workflow Validation And Dry-Run Coverage

**Files:**
- Modify: `tests/test_lisp_frontend_design_delta_recovery.py`
- Existing: `workflows/examples/lisp_frontend_design_delta_drain.yaml`

- [ ] **Step 1: Add validation smoke test**

Add a test that invokes the workflow loader or validation route against `workflows/examples/lisp_frontend_design_delta_drain.yaml` and asserts no schema errors for new artifact references.

Prefer an in-process loader test if existing tests use that pattern. Otherwise use a subprocess smoke test sparingly.

- [ ] **Step 2: Run collect-only**

Run: `python -m pytest --collect-only tests/test_lisp_frontend_design_delta_recovery.py -q`

Expected: all new tests collected.

- [ ] **Step 3: Run focused tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_design_delta_recovery.py -q
```

Expected: PASS.

- [ ] **Step 4: Run workflow dry-run**

Run:

```bash
python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml --dry-run \
  --input steering_path=docs/steering.md \
  --input target_design_path=docs/design/workflow_lisp_runtime_native_drain_authoring.md \
  --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md \
  --input progress_ledger_path=state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/progress_ledger.json \
  --input drain_state_root=state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain \
  --input run_state_target_path=state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain/run_state.json \
  --input drain_summary_target_path=artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain-summary.json \
  --input artifact_work_root=artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN \
  --input artifact_checks_root=artifacts/checks/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN \
  --input artifact_review_root=artifacts/review/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN \
  --input architecture_index_root=docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps
```

Expected: validation successful. Existing lint warnings are acceptable only if unchanged and unrelated.

- [ ] **Step 5: Commit**

```bash
git add tests/test_lisp_frontend_design_delta_recovery.py
git commit -m "Cover blocked gap plan rebase workflow validation"
```

## Task 6: Documentation And Prompt Hygiene

**Files:**
- Modify: `docs/workflow_drafting_guide.md` only if the new recovery pattern should be reusable beyond this workflow.
- Modify: `docs/index.md` only if a new reusable doc or prompt pattern becomes a routed concept.
- Modify: `workflows/README.md` only if the design delta drain description should mention plan-rebase recovery.

- [ ] **Step 1: Decide whether docs need updates**

If implementation only changes this workflow's internal recovery behavior, skip global docs.

If you introduce a reusable pattern, add a short drafting-guide note:

```markdown
When a recovery step revises a design surface, route execution-plan validity as
structured state. Do not rely on the reviser to incrementally patch a stale plan
when the revised design or prerequisite completion changes the baseline failure
surface.
```

- [ ] **Step 2: Run markdown and diff checks**

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 3: Commit docs if changed**

```bash
git add docs/workflow_drafting_guide.md docs/index.md workflows/README.md
git commit -m "Document recovered gap plan rebase routing"
```

Skip the commit if no docs changed.

## Task 7: Final Verification

**Files:**
- All touched files.

- [ ] **Step 1: Run focused unit tests**

```bash
python -m pytest tests/test_lisp_frontend_design_delta_recovery.py -q
```

Expected: PASS.

- [ ] **Step 2: Run related existing tests**

```bash
python -m pytest tests/test_loader_validation.py -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "blocked_recovery or design_delta_parent_drain" -q
```

Expected: PASS, or document unrelated pre-existing failures with exact failing tests.

- [ ] **Step 3: Run workflow dry-run**

Use the dry-run command from Task 5.

Expected: validation successful.

- [ ] **Step 4: Inspect staged diff**

```bash
git diff --stat
git diff --check
```

Expected: no unrelated files and no whitespace errors.

- [ ] **Step 5: Final commit if needed**

If any final verification-only fixes were made:

```bash
git add <exact touched files>
git commit -m "Finalize blocked gap plan rebase recovery"
```

## Risks And Guardrails

- Do not make prompt text manage loop counters or retries. The workflow routes `plan_disposition`; prompts only write artifacts and local judgments.
- Do not parse markdown review reports for routing. Use structured provider bundles and enum files.
- Do not allow `PLAN_REBASE_REQUIRED` to fall through to `RUN_RECOVERED_GAP`.
- Do not broaden this into a generic workflow engine feature. This plan is scoped to the Design Delta Drain YAML recovery path.
- Do not stage active run artifacts from `state/` or `artifacts/` unless a task explicitly creates a fixture under `tests/fixtures`.

## Success Criteria

- A gap design revision can explicitly say the associated execution plan needs full rebase.
- The workflow redrafts and reviews that plan before retrying the recovered gap.
- The workflow can retire a stale/superseded plan without executing old remediation steps.
- Run state records the disposition so future selection/recovery has durable evidence.
- Existing blocked recovery routes still dry-run and validate.
