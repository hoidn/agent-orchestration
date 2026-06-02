# Design Delta Blocked Implementation Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the design-delta drain classify blocked design-gap implementations from evidence and route recoverable blockers into gap-design or target-design revision before treating the item as terminally blocked.

**Architecture:** Keep workflow routing deterministic and use a provider only for the judgment-heavy question: whether the blocker is resolvable by revising the generated gap implementation architecture, by revising the durable target design, or not safely recoverable in-workflow. Newly blocked items and prior blocked design gaps should share the same recovery decision contract, then the workflow runs the selected reviewed revision path or records/keeps a terminal block.

**Tech Stack:** agent-orchestration DSL v2.14 YAML, provider prompt assets, Python command adapters under `workflows/library/scripts/`, pytest runtime tests, orchestrator dry-run validation.

---

## Required Context

Read before implementation:

- `docs/index.md`
- `docs/workflow_drafting_guide.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/dependencies.md`
- `specs/providers.md`
- `workflows/README.md`
- `docs/plans/2026-06-01-design-delta-blocker-revision-loop.md`

Observed failure this plan addresses:

- A design-gap implementation reported `implementation_state=BLOCKED` with `blocker_class=external_dependency_outside_authority`.
- In this workflow, that usually means "outside the implementation agent's approved slice," not "outside all workflow authority." The progress report said the bounded implementation architecture was under-scoped for the target design, which should normally trigger gap-design revision first.
- Current code treats only `roadmap_conflict` as design-revisable, so the workflow records `implementation_blocked` instead of revising the target `.md`.

## File Structure

- Modify: `workflows/library/scripts/classify_lisp_frontend_work_item_terminal.py`
  - Stop deciding design-revision eligibility from `blocker_class`; blocked implementation attempts route to `IMPLEMENTATION_BLOCKED`.
- Modify: `workflows/library/scripts/detect_lisp_frontend_prior_blocked_design_gap.py`
  - Detect prior blocked design gaps with progress evidence as recovery candidates without keyword-gating on `roadmap_conflict`.
- Create: `workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md`
  - Provider prompt that returns a structured recovery decision from blocker evidence.
- Modify: `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml`
  - In the `IMPLEMENTATION_BLOCKED` branch, run recovery classification for design-gap items, then run gap-design revision, target-design revision, or terminal blocked recording.
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
  - In prior-blocked startup recovery, classify the prior blocker before running target-design revision; terminal prior blockers remain blocked and selection continues.
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`
  - Add script and runtime coverage for ambiguous blockers, prior blocked recovery, and terminal blockers.

## Recovery Contract

Provider judgment output:

```json
{
  "blocked_recovery_route": "GAP_DESIGN_REVISION_REQUIRED | TARGET_DESIGN_REVISION_REQUIRED | TERMINAL_BLOCKED",
  "reason": "implementation_architecture_under_scoped | target_design_contract_gap | true_external_dependency | user_decision_required | unsupported_blocker",
  "summary": ""
}
```

Routing rules:

- `GAP_DESIGN_REVISION_REQUIRED`: revise/review the selected gap's `implementation_architecture.md`, regenerate its work-item context/checks, then rerun plan/implementation for the same gap or return `CONTINUE` with the gap unblocked for reselection.
- `TARGET_DESIGN_REVISION_REQUIRED`: revise/review the durable target design, record a `design_revision` event, and return `CONTINUE`.
- `TERMINAL_BLOCKED`: record a newly blocked item as blocked; for a prior blocked item, leave it blocked and continue normal selection.
- The provider may judge evidence, but only workflow YAML/scripts decide whether the drain continues, blocks, or revises.
- Do not retry implementation unless a gap-design or target-design revision was reviewed and approved.

Distinction:

- Gap design revision changes the generated implementation architecture for one selected design gap. Use it when the target design is coherent but the selected gap slice, dependencies, or execution plan were under-scoped.
- Target design revision changes the durable target `.md`. Use it only when implementation evidence shows the target design's own contract is missing, contradictory, or wrong.

## Task 1: Characterize Current Misrouting

**Files:**

- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add a failing terminal-classifier test**

Add a test that writes `implementation_state.json` with:

```json
{
  "implementation_state": "BLOCKED",
  "blocker_class": "external_dependency_outside_authority"
}
```

Run `classify_lisp_frontend_work_item_terminal.py` with `--work-item-source DESIGN_GAP`.

Assert the output is:

```json
{
  "terminal_route": "IMPLEMENTATION_BLOCKED",
  "block_reason": "implementation_blocked"
}
```

This locks in that design-revision eligibility is no longer decided by this script.

- [ ] **Step 2: Add a failing prior-blocked detector test**

Seed `run_state.json` with one blocked design gap and write its progress report under:

```text
artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/progress_report.md
```

Use progress text that mentions an under-scoped implementation architecture but does not contain `roadmap_conflict`.

Assert `detect_lisp_frontend_prior_blocked_design_gap.py` emits `RECOVER_BLOCKED_DESIGN_GAP` and copies the progress report.

- [ ] **Step 3: Run the characterization tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "work_item_terminal or prior_blocked_design_gap" -q
```

Expected: the new tests fail on the current `roadmap_conflict` keyword gate.

## Task 2: Move Eligibility Out Of Terminal Scripts

**Files:**

- Modify: `workflows/library/scripts/classify_lisp_frontend_work_item_terminal.py`
- Modify: `workflows/library/scripts/detect_lisp_frontend_prior_blocked_design_gap.py`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Simplify work-item terminal classification**

Change `classify_lisp_frontend_work_item_terminal.py` so every `BLOCKED` implementation state maps to:

```json
{
  "terminal_route": "IMPLEMENTATION_BLOCKED",
  "block_reason": "implementation_blocked"
}
```

Remove `REVISION_ALLOWED_BLOCKERS` from this script.

- [ ] **Step 2: Broaden prior blocked detection**

Change `detect_lisp_frontend_prior_blocked_design_gap.py` so a design gap with:

- `reason == "implementation_blocked"`, and
- an existing progress report

is emitted as `RECOVER_BLOCKED_DESIGN_GAP` without requiring `roadmap_conflict` in the report text.

Keep the progress-report copy behavior.

- [ ] **Step 3: Run focused script tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "work_item_terminal or prior_blocked_design_gap" -q
```

Expected: the characterization tests pass.

- [ ] **Step 4: Commit**

```bash
git add workflows/library/scripts/classify_lisp_frontend_work_item_terminal.py \
  workflows/library/scripts/detect_lisp_frontend_prior_blocked_design_gap.py \
  tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "fix: defer design blocker recovery classification"
```

## Task 3: Add Structured Recovery Judgment Prompt

**Files:**

- Create: `workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add prompt-surface test**

Add a test that reads the new prompt and asserts it:

- asks for `GAP_DESIGN_REVISION_REQUIRED`, `TARGET_DESIGN_REVISION_REQUIRED`, or `TERMINAL_BLOCKED`;
- mentions target design and blocker evidence;
- does not tell the provider to continue, retry, or mark the drain blocked.

- [ ] **Step 2: Write the prompt**

Create the prompt with this content:

```markdown
You are classifying a blocked implementation attempt.

Read the target design, baseline design, implementation architecture if present,
approved plan if present, implementation state, and progress report.

Choose `GAP_DESIGN_REVISION_REQUIRED` when the target design is coherent but the
selected gap's implementation architecture, decomposition, dependencies, or
approved implementation slice is under-scoped.

Choose `TARGET_DESIGN_REVISION_REQUIRED` only when the blocker shows that the
durable target design itself is under-specified, internally inconsistent, or
missing a contract needed to implement the selected design gap.

Choose `TERMINAL_BLOCKED` for true external dependencies, missing user decisions,
missing resources, unsupported tools, or blockers that cannot be resolved by a
bounded gap-design or target-design revision.

Write one JSON bundle at the required output path:

{
  "blocked_recovery_route": "GAP_DESIGN_REVISION_REQUIRED | TARGET_DESIGN_REVISION_REQUIRED | TERMINAL_BLOCKED",
  "reason": "implementation_architecture_under_scoped | target_design_contract_gap | true_external_dependency | user_decision_required | unsupported_blocker",
  "summary": ""
}
```

- [ ] **Step 3: Run prompt test**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "blocked_implementation_recovery_prompt" -q
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md \
  tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "docs: add blocked implementation recovery classifier prompt"
```

## Task 4: Route Newly Blocked Design Gaps Through Recovery Classification

**Files:**

- Modify: `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add workflow-structure test**

Add a test that asserts the `IMPLEMENTATION_BLOCKED` case:

- matches on `work_item_source`;
- records backlog-item blockers directly as terminal blocked;
- for `DESIGN_GAP`, calls `ClassifyBlockedImplementationRecovery`;
- matches `blocked_recovery_route`;
- sends `GAP_DESIGN_REVISION_REQUIRED` to a gap-design revise/review path;
- sends `TARGET_DESIGN_REVISION_REQUIRED` to `ReviewTargetDesignRevisionLoop` / `RecordDesignRevisionOutcome`;
- sends `TERMINAL_BLOCKED` to `RecordImplementationBlocked`.

- [ ] **Step 2: Run structure test to verify failure**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "blocked_implementation_recovery_branch" -q
```

Expected: fail until the YAML route is updated.

- [ ] **Step 3: Add `ClassifyBlockedImplementationRecovery`**

Inside the `IMPLEMENTATION_BLOCKED` branch for design gaps, add a provider step:

```yaml
- name: ClassifyBlockedImplementationRecovery
  id: classify_blocked_implementation_recovery
  provider: ${inputs.implementation_review_provider}
  asset_file: prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md
  timeout_sec: 1800
  depends_on:
    required:
      - ${inputs.target_design_path}
      - ${inputs.baseline_design_path}
      - ${steps.ResolveWorkItemInputs.artifacts.implementation_phase_state_root}/implementation_state.json
      - ${steps.ResolveWorkItemInputs.artifacts.progress_report_target_path}
    optional:
      - ${steps.ResolveWorkItemInputs.artifacts.plan_target_path}
      - ${steps.ResolveWorkItemInputs.artifacts.work_item_context_path}
    inject:
      mode: content
  output_bundle:
    path: ${inputs.state_root}/blocked-implementation-recovery.json
    fields:
      - name: blocked_recovery_route
        json_pointer: /blocked_recovery_route
        type: enum
        allowed: ["GAP_DESIGN_REVISION_REQUIRED", "TARGET_DESIGN_REVISION_REQUIRED", "TERMINAL_BLOCKED"]
      - name: reason
        json_pointer: /reason
        type: enum
        allowed:
          - implementation_architecture_under_scoped
          - target_design_contract_gap
          - true_external_dependency
          - user_decision_required
          - unsupported_blocker
```

- [ ] **Step 4: Wire the route**

Match `blocked_recovery_route`:

- `GAP_DESIGN_REVISION_REQUIRED`: rerun or call the design-gap architecture revision/review path for the selected gap, then keep the gap unblocked for a fresh planning pass.
- `TARGET_DESIGN_REVISION_REQUIRED`: reuse the existing target-design revision/review path and record `design_revision`.
- `TERMINAL_BLOCKED`: call `update_lisp_frontend_run_state.py blocked` with reason `implementation_blocked`.

Keep work-item outputs as `drain_status` and `item_summary_path`.

- [ ] **Step 5: Run structure test**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "blocked_implementation_recovery_branch" -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add workflows/library/lisp_frontend_design_delta_work_item.v214.yaml \
  tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "feat: classify blocked design-gap recovery"
```

## Task 5: Classify Prior Blocked Design Gaps Before Startup Recovery

**Files:**

- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add startup recovery structure test**

Assert `RoutePriorBlockedDesignGapRecovery.RECOVER_BLOCKED_DESIGN_GAP` contains:

- `ClassifyPriorBlockedImplementationRecovery`;
- a match on `blocked_recovery_route`;
- `GAP_DESIGN_REVISION_REQUIRED` path that reruns or calls the prior gap architecture revision/review path;
- `TARGET_DESIGN_REVISION_REQUIRED` path that runs `RevisePriorBlockedDesignGap` and review;
- `TERMINAL_BLOCKED` path that leaves the item blocked and emits `prior_recovery_status=CONTINUE`.

- [ ] **Step 2: Run structure test to verify failure**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "prior_blocked_recovery_classification" -q
```

Expected: fail until startup route is updated.

- [ ] **Step 3: Add prior-blocked classifier provider**

Before `RevisePriorBlockedDesignGap`, add a provider step that uses the same prompt and consumes:

- target design;
- baseline design;
- copied prior blocked progress report;
- prior recovery JSON.

Write output bundle to:

```text
${inputs.drain_state_root}/prior-blocked-recovery-decision.json
```

- [ ] **Step 4: Route terminal prior blockers to continue selection**

For `TERMINAL_BLOCKED`, write `prior_recovery_status=CONTINUE`.

Do not remove the existing blocked run-state entry. The selector can skip it and continue to other work; if no work remains, the selector determines the final drain status.

- [ ] **Step 5: Run structure test**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "prior_blocked_recovery_classification" -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add workflows/examples/lisp_frontend_design_delta_drain.yaml \
  tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "feat: classify prior blocked design-gap recovery"
```

## Task 6: Add Runtime Coverage For Ambiguous Blockers

**Files:**

- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add provider writers**

Add fake provider helpers:

- `_write_blocked_external_design_gap_evidence`: writes `implementation_state=BLOCKED`, `blocker_class=external_dependency_outside_authority`, and a progress report saying the implementation architecture is under-scoped.
- `_classify_blocked_recovery_design_revision_required`: writes `blocked_recovery_route=DESIGN_REVISION_REQUIRED`.
- `_classify_blocked_recovery_terminal`: writes `blocked_recovery_route=TERMINAL_BLOCKED`.

- [ ] **Step 2: Add newly blocked design-revision runtime test**

Provider sequence:

```python
[
    ("SelectNextWork", _write_selector_design_gap),
    ("DraftDesignGapArchitecture", _write_design_gap_architecture),
    ("DraftPlan", _write_plan),
    ("ReviewPlan", _write_plan_review),
    ("ExecuteImplementation", _write_blocked_external_design_gap_evidence),
    ("ClassifyBlockedImplementationRecovery", _classify_blocked_recovery_design_revision_required),
    ("ReviseTargetDesignForBlocker", _revise_target_design_for_blocker),
    ("ReviewTargetDesignRevision", _write_design_revision_review_approve),
    ("SelectNextWork", _write_selector_done),
]
```

Assert:

- run completes;
- drain summary is `DONE`;
- run-state history contains `design_revision`;
- the design gap is not in `blocked_design_gaps`;
- target design was edited.

- [ ] **Step 3: Add terminal ambiguous-blocker runtime test**

Use the same blocked implementation writer, but have the classifier provider write `TERMINAL_BLOCKED`.

Assert:

- `ReviseTargetDesignForBlocker` was not called;
- drain summary is `BLOCKED`;
- blocked design gap reason is `implementation_blocked`.

- [ ] **Step 4: Add prior-blocked startup runtime test**

Seed a prior blocked design gap whose progress report lacks `roadmap_conflict` but describes under-scoped implementation architecture.

Provider sequence:

```python
[
    ("ClassifyPriorBlockedImplementationRecovery", _classify_blocked_recovery_design_revision_required),
    ("RevisePriorBlockedDesignGap", _revise_prior_blocked_design_gap),
    ("ReviewPriorBlockedDesignRevision", _write_prior_design_revision_review_approve),
    ("SelectNextWork", _write_selector_done),
]
```

Assert recovery happens before selection and records the correct revision event for the selected route.

- [ ] **Step 5: Run focused runtime tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "blocked_recovery or prior_blocked" -q
```

Expected: all new runtime tests pass.

- [ ] **Step 6: Commit**

```bash
git add tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "test: cover ambiguous blocked implementation recovery"
```

## Task 7: Validate The Workflow Stack

**Files:**

- Modify only if needed: `workflows/README.md`

- [ ] **Step 1: Collect tests**

Run:

```bash
python -m pytest --collect-only tests/test_lisp_frontend_autonomous_drain_runtime.py -q
```

Expected: collection succeeds.

- [ ] **Step 2: Run the target test module**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q
```

Expected: module passes.

- [ ] **Step 3: Run orchestrator dry-run**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml \
  --dry-run \
  --input steering_path=docs/steering.md \
  --input target_design_path=docs/design/workflow_lisp_key_migration_parity_architecture.md \
  --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md \
  --input progress_ledger_path=state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json \
  --input drain_state_root=state/LISP-MIGRATION-PARITY-DRAIN/dry-run-drain \
  --input run_state_target_path=state/LISP-MIGRATION-PARITY-DRAIN/dry-run-drain/run_state.json \
  --input drain_summary_target_path=artifacts/work/LISP-MIGRATION-PARITY-DRAIN/dry-run-drain-summary.json \
  --input artifact_work_root=artifacts/work/LISP-MIGRATION-PARITY-DRAIN \
  --input artifact_checks_root=artifacts/checks/LISP-MIGRATION-PARITY-DRAIN \
  --input artifact_review_root=artifacts/review/LISP-MIGRATION-PARITY-DRAIN
```

Expected: dry-run validation succeeds.

- [ ] **Step 4: Inspect the diff for ownership boundaries**

Run:

```bash
git diff -- workflows/examples/lisp_frontend_design_delta_drain.yaml \
  workflows/library/lisp_frontend_design_delta_work_item.v214.yaml \
  workflows/library/scripts \
  workflows/library/prompts/lisp_frontend_design_delta_work_item \
  tests/test_lisp_frontend_autonomous_drain_runtime.py
```

Confirm:

- prompts classify or revise only; they do not manage drain routing;
- YAML/scripts own route decisions and run-state writes;
- prior blocked recovery and newly blocked recovery share the same decision vocabulary;
- terminal blockers are still recorded honestly.

- [ ] **Step 5: Commit docs/catalog cleanup if needed**

If `workflows/README.md` needs a catalog note, update it and commit:

```bash
git add workflows/README.md
git commit -m "docs: note blocked implementation recovery route"
```

Skip this step if no catalog change is needed.

## Non-Goals

- Do not broaden every `external_dependency_outside_authority` blocker automatically.
- Do not parse markdown reports in scripts to decide workflow state.
- Do not make provider prompts write run-state files or choose drain status.
- Do not rerun implementation without an approved gap-design or target-design revision.
- Do not change the shared non-design-delta Lisp frontend drain in this slice.

## Handoff Notes

This is a follow-up to `docs/plans/2026-06-01-design-delta-blocker-revision-loop.md`. That plan added a target-design revision path but left eligibility tied to a narrow `roadmap_conflict` token. This plan makes recovery eligibility a structured judgment step and distinguishes gap-design revision from target-design revision, so the workflow can recover from under-scoped implementation architecture blockers without laundering true external blockers into design churn.
