# Workflow Audit Tier Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees.

**Goal:** Implement all three tiers of the 2026-07-01 workflow prompt/mechanics audit: remove counterproductive rewrites and self-defeating safety machinery, close the incident (stale-requirement entrenchment) pattern at every remaining layer, fix hard routing bugs in the neurips drain, and delete stale/orphaned surfaces.

**Architecture:** Fixes are grouped by surface so each task is independently verifiable. Script fixes are behavior *deletions* wherever possible (delete the user-decision rewrite, stop counting non-progress events as progress). Prompt fixes are subtractive or single-sentence ports of the already-landed incident fixes. YAML fixes use existing DSL primitives (`on_exhausted`, `when` guards) — no new machinery.

**Tech Stack:** Python scripts under `workflows/library/scripts/`, workflow YAML (DSL v2.14), Workflow Lisp `.orc`, markdown prompts, pytest.

## Global Constraints

- Run all commands from the repo root `/home/ollie/Documents/agent-orchestration`.
- **Commit policy — pre-dirty files:** the working tree carries large in-flight migration edits. Task 0 records the pre-dirty file set. Tasks `git add` ONLY files that were clean at plan start. Files that were already modified (e.g. `workflows/library/lisp_frontend_design_delta/projections.orc`, `workflows/library/lisp_frontend_design_delta_done_review.v214.yaml`, `tests/test_lisp_frontend_autonomous_drain_runtime.py`, `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml`) get edited but are left uncommitted; the final report lists them.
- Commit messages: plain descriptive text. NEVER mention Claude/assistant or add Co-Authored-By trailers (repo rule).
- Never use `--no-verify`. Never disable tests — update them to the new intended behavior.
- Prefer the narrowest pytest selectors first. If tests are added/renamed, run `pytest --collect-only` on the module.
- After YAML/prompt changes, run the loader smoke check (see Task 14 helper) on every touched workflow YAML.
- Do not touch `orchestrator/` source (in-flight migration surface) except where a task explicitly says so (none do).
- The `.orc` files under `workflows/library/lisp_frontend_design_delta/` and their fixture mirrors are pre-dirty; edit precisely and minimally.

## Deferred (explicitly out of scope, with rationale)

- `.orc` selector prompt-schema mismatch and `waiting_on_*` fields missing from `.orc` type records (selector-audit F8, recovery-audit F7): the `.orc` migration lane is mid-flight in the working tree; changing typed records now would collide with it. Record as follow-up.
- neurips `gap_policy: draft_backlog_item` completion semantics (when should a steered drain with gap-minting declare DONE?): needs a product decision; Task 11 fixes the deterministic `block`-policy case only.
- Routing `PLAN_REVIEW_EXHAUSTED` through the blocked-recovery classifier (plan-audit F3 workflow-side): structural workflow change; Task 5 lands the prompt-side escape instead. Record as follow-up.
- Gap-doc `Status: completed` stamping (selector-audit F14): new machinery, belt-and-braces only.

---

### Task 0: Record pre-dirty set and baseline

**Files:** none modified.

- [ ] **Step 1:** `git status --porcelain > /tmp/claude-1000/-home-ollie-Documents-agent-orchestration/a372f45b-c8d5-4bd2-a499-b5fd21843698/scratchpad/pre_dirty.txt` and keep this file for the commit policy.
- [ ] **Step 2:** Confirm baseline health of the test modules this plan touches (record failures that pre-exist):
```bash
python -m pytest tests/test_workflow_non_progress_recovery.py tests/test_workflow_non_progress_step_back_demo.py tests/test_neurips_backlog_roadmap_gate.py -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q -k "user_decision" 
python -m pytest tests/test_workflow_lisp_projection_dual_run.py -q
```
Record pass/fail counts in the scratchpad; pre-existing failures are not this plan's regressions but must not grow.

---

### Task 1: Honor terminal user-decision classifications (delete the rewrite)

The classifier's `TERMINAL_BLOCKED / user_decision_required` verdict is silently rewritten to `GAP_DESIGN_REVISION_REQUIRED / implementation_architecture_under_scoped` by keyword-sniffing in the script and unconditionally in the `.orc` projection. Delete both. The anti-abuse guard lives where it belongs: in the classifier prompt (already instructs against using `user_decision_required` for repo-local issues).

**Files:**
- Modify: `workflows/library/scripts/select_lisp_frontend_blocked_recovery_route.py` (delete `TERMINAL_USER_DECISION_EVIDENCE` at ~:21-36 and the body of `_normalize_design_gap_recovery` at ~:39-47)
- Modify: `workflows/library/lisp_frontend_design_delta/projections.orc` (~:130-145, `rewrite-user-decision`) — pre-dirty, no commit
- Modify: `tests/fixtures/workflow_lisp/valid/design_delta_projection_runtime_support/projections.orc` and `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/projections.orc` (same deletion; check pre-dirty status individually)
- Modify: `workflows/examples/inputs/workflow_lisp_migrations/design_delta_projection_dual_run_vectors.json` (vector `blocked_recovery_terminal_user_decision_rewrite`)
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py:1835-1873` — pre-dirty, no commit

- [ ] **Step 1:** In the script, delete the `TERMINAL_USER_DECISION_EVIDENCE` tuple and reduce the normalizer to a pass-through:
```python
def _normalize_design_gap_recovery(route: str, reason: str, bundle: dict[str, Any]) -> tuple[str, str]:
    return route, reason
```
Then inline/remove it if it has a single call site (prefer deleting the function and its call).
- [ ] **Step 2:** In `projections.orc` (all three copies), remove the `rewrite-user-decision` binding and its `(if rewrite-user-decision ...)` branch so `TERMINAL_BLOCKED` flows through like the other routes. Keep the `is-backlog-item` branch unchanged.
- [ ] **Step 3:** In the dual-run vectors file, update vector `blocked_recovery_terminal_user_decision_rewrite`: rename `id` to `blocked_recovery_terminal_user_decision_honored` and set:
```json
"expected_result": { "variant": "TERMINAL_BLOCKED", "reason": "user_decision_required" }
```
- [ ] **Step 4:** Update `test_blocked_recovery_user_decision_with_repo_scope_evidence_is_recoverable` (line 1835): rename to `test_blocked_recovery_user_decision_classification_is_honored` and change the expected output to:
```python
    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "blocked_recovery_route": "TERMINAL_BLOCKED",
        "reason": "user_decision_required",
    }
```
The marker-phrase tests at :1876+, :1912+ etc. already expect terminal-stays-terminal and should now pass unchanged — verify, and delete any test whose sole purpose was asserting the rewrite fires (search the module for `implementation_architecture_under_scoped` assertions paired with `user_decision_required` inputs). Also check `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py:5316` context; update only if it asserts the rewrite.
- [ ] **Step 5:** Verify:
```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q -k "user_decision"
python -m pytest tests/test_workflow_lisp_projection_dual_run.py -q
```
Expected: PASS (or no worse than Task 0 baseline for unrelated pre-existing failures).
- [ ] **Step 6:** Commit only clean-at-start files (`select_lisp_frontend_blocked_recovery_route.py`, vectors file, fixture mirrors if clean): `git commit -m "Honor terminal user-decision blocked-recovery classifications"`

---

### Task 2: Make progress signals truthful (step-back and rejected revisions are not progress)

**Files:**
- Modify: `workflows/library/scripts/project_lisp_frontend_progress_signals.py:117-125`
- Test: `tests/test_workflow_non_progress_recovery.py` (evaluator tests use synthetic events — unaffected); check `tests/golden_state.py` and `tests/test_lisp_frontend_autonomous_drain_runtime.py` for projection assertions that encode the old semantics — pre-dirty, edit without commit.

**Interfaces:** Produces events where `blocked_recovery_review_revise` has `plan_revised=True, accepted_change=False, outcome="blocked"` (making the `plan_churn_without_outcome_change` trigger satisfiable) and `step_back` has `accepted_change=False` (step-backs no longer erase the evaluator window).

- [ ] **Step 1:** Change the projection:
```python
        plan_revised = event_name in {"plan_revision", "gap_design_revision", "design_revision", "blocked_recovery_review_revise"}
        step_back_recorded = event_name == "step_back"
        accepted_change = (
            event_name == "completed"
            or (plan_revised and event_name != "blocked_recovery_review_revise")
            or dependency_edge_event == "retry_ready"
        )
```
(Only two behavioral deletions: `step_back_recorded` leaves the `accepted_change` disjunction; `blocked_recovery_review_revise` is excluded from it.)
- [ ] **Step 2:** Add behavioral tests to `tests/test_workflow_non_progress_recovery.py` (they exercise the projection + evaluator together; use the module's existing `_event` helper or write projection-level tests in the module that covers `project_lisp_frontend_progress_signals.py` — find it with `grep -rn "project_lisp_frontend_progress_signals" tests/`):
```python
def test_rejected_blocked_revision_is_not_an_accepted_change():
    # project a history: blocked, blocked_recovery_review_revise, blocked, blocked_recovery_review_revise
    # evaluator with plan_churn_threshold=2 must emit plan_churn_without_outcome_change
```
Write the real test against the actual helper APIs found in the covering module; assert the trigger fires and that a `step_back` event between blocks does NOT reset `_unresolved_suffix` (repeated-blocker trigger still fires).
- [ ] **Step 3:** Run and fix any projection-consuming tests that asserted old semantics:
```bash
python -m pytest tests/test_workflow_non_progress_recovery.py -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q -k "progress or non_progress or step_back"
```
- [ ] **Step 4:** Commit clean files: `git commit -m "Stop counting step-backs and rejected revisions as accepted changes"`

---

### Task 3: Feed revision-review feedback into the next revision attempt

On the TARGET-route REVISE loop the reviewer's report is discarded; each fresh reviser re-revises blind.

**Files:**
- Modify: `workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py` (REVISE branch ~:624-643)
- Modify: `workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py` (recovery-bundle construction ~:352-370)
- Modify: `workflows/library/prompts/lisp_frontend_design_delta_work_item/revise_prior_blocked_design_gap.md` (one sentence)

- [ ] **Step 1:** In the record script's review-REVISE branch, after the existing `_append_recovery_review_revise_event` call, copy the review report to a stable path:
```python
    feedback_target = drain_state_root / "blocked-revision-review-feedback.md"
    feedback_target.write_text(review_report_path.read_text(encoding="utf-8"), encoding="utf-8")
```
(Adapt variable names to the function's actual locals — the review report path is already in scope in that branch; read the function first.)
- [ ] **Step 2:** In the detect script, when building the recovery bundle, include the feedback pointer when the file exists:
```python
    feedback = drain_state_root / "blocked-revision-review-feedback.md"
    if feedback.is_file():
        bundle["prior_revision_review_feedback_path"] = _repo_relpath(feedback)
```
- [ ] **Step 3:** Append one sentence to the reviser prompt after the remove/narrow/split paragraph: `If the recovery bundle names prior revision review feedback, read it and resolve the reviewer's concrete findings rather than repeating the rejected revision.`
- [ ] **Step 4:** Add a behavioral test in the module covering `record_lisp_frontend_blocked_recovery_outcome.py` (find via grep): after a review-REVISE outcome, the stable feedback file exists and the next detect-produced bundle carries `prior_revision_review_feedback_path`.
- [ ] **Step 5:** Run the covering test module selectors; commit clean files: `git commit -m "Carry blocked-revision review feedback into the next revision attempt"`

---

### Task 4: Done-review dedup guard

**Files:**
- Modify: `workflows/library/scripts/project_lisp_frontend_done_review.py` (add optional `--run-state-path`, guard `_rejection_payload` call)
- Modify: `workflows/library/lisp_frontend_design_delta_done_review.v214.yaml` `ProjectDoneReview` step (pass the arg) — pre-dirty, no commit
- Modify: `workflows/library/prompts/lisp_frontend_selector/review_done_design_delta.md` (one sentence)

- [ ] **Step 1:** First `grep -n "completed_design_gaps\|blocked_design_gaps" workflows/library/scripts/update_lisp_frontend_run_state.py` to confirm the run-state key names; adapt the code below to the real keys.
- [ ] **Step 2:** In the projection script add `parser.add_argument("--run-state-path", required=False)` and, for `REJECT_DONE` when the arg is provided and the file exists:
```python
        run_state = json.loads((REPO_ROOT / _safe_relpath(args.run_state_path, under="state", must_exist=True)).read_text(encoding="utf-8"))
        gap_id = str(review.get("design_gap_id") or "").strip()
        completed = {str(x) for x in (run_state.get("completed_design_gaps") or [])}
        blocked_value = run_state.get("blocked_design_gaps")
        blocked = {str(k) for k in blocked_value} if isinstance(blocked_value, dict) else {str(x) for x in (blocked_value or [])}
        if gap_id in completed | blocked:
            raise SystemExit(
                f"done-review rejection re-mints a known design gap: {gap_id}; "
                "route it through blocked-gap recovery or approve DONE"
            )
```
- [ ] **Step 3:** In the done-review composite YAML pass `--run-state-path` with the run-state input already available in that workflow (grep the file for `run_state` to find the input name).
- [ ] **Step 4:** Add one sentence to the done-review prompt: `Before rejecting DONE, check the manifest's attempt history; do not re-propose a design gap that is already completed or blocked.`
- [ ] **Step 5:** Add a script-level test (same pattern as existing `_run_script` tests in `tests/test_lisp_frontend_autonomous_drain_runtime.py`): a REJECT_DONE review naming a gap in `blocked_design_gaps` exits nonzero. Run it plus the loader smoke on the composite YAML. Commit clean files: `git commit -m "Reject done-review gap minting for known completed or blocked gaps"`

---

### Task 5: Port the incident discipline across all prompt variants

All edits are one-to-three sentences; exact text below. No other wording changes.

**Files (all under `workflows/library/prompts/`):**
1. `lisp_frontend_design_delta_implementation_phase/review_implementation.md`
2. `lisp_frontend_implementation_phase/implement_plan.md`
3. `lisp_frontend_design_gap_architect/draft_implementation_architecture.md` and `lisp_frontend_design_delta_design_gap_architect/draft_implementation_architecture.md`
4. `lisp_frontend_design_gap_architect/review_implementation_architecture.md` and `lisp_frontend_design_delta_design_gap_architect/review_implementation_architecture.md`
5. `lisp_frontend_design_delta_plan_phase/draft_plan.md`, `review_plan.md`, `revise_plan.md`
6. `lisp_frontend_plan_phase/review_plan.md`, `revise_plan.md`, `draft_plan.md`
7. `lisp_frontend_implementation_phase/fix_implementation.md` and `lisp_frontend_design_delta_implementation_phase/fix_implementation.md`

- [ ] **Step 1 (delta reviewer carve-outs):** Copy from `lisp_frontend_implementation_phase/review_implementation.md` the blocking-issue classification bullet (its lines ~73-76: classify each blocking issue as implementation defect / missing evidence / invalid or non-runnable gate / environment blocker / pre-existing drift, and do not treat invalid gates or environment issues as implementation defects) and the evidence carve-out (~:16-23) into `lisp_frontend_design_delta_implementation_phase/review_implementation.md`, adapting only design nouns (target design/gap architecture). Also qualify its approval bar: `missing required check` → `missing explicitly-blocking check`.
- [ ] **Step 2 (generic implementer liveness):** Into `lisp_frontend_implementation_phase/implement_plan.md` after the blocked-report sentence, insert exactly:
```text
Report the conflict as observed evidence; a failing check or legacy behavior is
not by itself a preservation requirement, so do not state one as a requirement
unless you verified its consumer is live in the current checkout. If a check
can only pass by doing something the approved plan forbids, do not make that
change; report `BLOCKED` with the conflict.
```
- [ ] **Step 3 (architect traceability):** In both `draft_implementation_architecture.md` files, append to the acceptance/check-command instruction: `Every acceptance condition and check command must be traceable to the target design or to behavior whose consumer you verified is live in the current checkout; classify any failing pre-existing check as a live contract to satisfy or a stale artifact to exclude before including it.` In both `review_implementation_architecture.md` files, extend the rejection sentence with: `Also reject requirements or check commands not traceable to the target design or to verified current behavior.`
- [ ] **Step 4 (delta plan authority):** In the three `lisp_frontend_design_delta_plan_phase` prompts, add "gap architecture" to the consumed-authority phrasing (e.g. `draft_plan.md:3` "Use the consumed target design, baseline design, and work-item context" → "...baseline design, gap architecture, and work-item context"; make the reviewer reject plans that contradict the gap architecture; make the reviser preserve it).
- [ ] **Step 5 (cross-port thresholds/guardrails):** Port the delta relaxation into `lisp_frontend_plan_phase/review_plan.md` (REVISE only for concrete high-severity gaps; approve medium verification gaps with notes — mirror the delta wording). Port the generic paperwork guardrail sentence (`Do not plan manifest, conformance, parity, summary, inventory, or status-label work as a blocking implementation task...` — copy verbatim from `lisp_frontend_plan_phase/draft_plan.md:8-11`) into the three delta plan prompts.
- [ ] **Step 6 (stale-architecture escape):** Append to both families' `review_plan.md` and `revise_plan.md`: `If the plan cannot be made executable because the consumed design or gap architecture requires a route, mechanism, or artifact that is absent from or contradicted by the current checkout, name that requirement explicitly in the report as the causal finding instead of iterating.`
- [ ] **Step 7 (fix escapes):** In generic `fix_implementation.md` append: `Report a blocker instead of a fix only when a finding cannot be satisfied because the approved binding surface is absent, contradictory, or would require changing the approved contract.` In delta `fix_implementation.md` replace the incident-pinned sentence (~:11-12, the one enumerating "hidden/system-owned context, generated path, checkpoint, or boundary findings...") with: `Do not satisfy a finding by fabricating records or hard-coding generated values in authored source; use the approved binding surface.`
- [ ] **Step 8:** Verify no tests assert the old literal wording (`grep -rn "smallest principled\|medium-or-higher" tests/ | grep -v fixture`), run `python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q -k "prompt"`, and the loader smoke on `workflows/library/lisp_frontend_design_delta_implementation_phase.v214.yaml` + `workflows/library/lisp_frontend_implementation_phase.v214.yaml`. Commit: `git commit -m "Port incident-recovery discipline across prompt variants"`

---

### Task 6: One-object classifier output contract

**Files:** Modify `workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md`

- [ ] **Step 1:** Delete the trailing PREREQUISITE paragraph ("When `blocked_recovery_route` is `PREREQUISITE_GAP_REQUIRED`, include only...") and its second fenced JSON block. Extend the single example object instead:
```json
{
  "blocked_recovery_route": "GAP_DESIGN_REVISION_REQUIRED | TARGET_DESIGN_REVISION_REQUIRED | PREREQUISITE_GAP_REQUIRED | TERMINAL_BLOCKED",
  "reason": "implementation_architecture_under_scoped | target_design_contract_gap | prerequisite_gap_required | true_external_dependency | user_decision_required | unsupported_blocker",
  "summary": "",
  "waiting_on_work_id": "<required for PREREQUISITE_GAP_REQUIRED, else omit>",
  "waiting_on_work_source": "DESIGN_GAP | BACKLOG_ITEM (required for PREREQUISITE_GAP_REQUIRED, else omit)"
}
```
Keep the sentence `If no safe prerequisite can be identified, use TERMINAL_BLOCKED with reason: unsupported_blocker.`
- [ ] **Step 2:** Loader smoke on `workflows/examples/lisp_frontend_design_delta_drain.yaml`; commit: `git commit -m "Collapse blocked-recovery classifier output to one JSON object"`

---

### Task 7: Recovered retries keep their real check commands

**Files:** Modify `workflows/library/scripts/materialize_lisp_frontend_recovered_design_gap_draft.py` (~:110-165)

- [ ] **Step 1:** In `_materialize_retry_bundle`, before writing the regenerated trivial checks, reuse the previous VALID bundle's checks when available:
```python
    checks = [
        f"test -f {architecture_path.as_posix()}",
        "python -m compileall orchestrator/workflow_lisp",
    ]
    if (REPO_ROOT / plan_path).exists():
        checks.insert(1, f"test -f {plan_path.as_posix()}")
    if previous is not None:
        prev_checks_rel = str(previous.get("check_commands_path") or "")
        prev_checks_file = REPO_ROOT / prev_checks_rel if prev_checks_rel else None
        if prev_checks_file is not None and prev_checks_file.is_file():
            try:
                prev_checks = json.loads(prev_checks_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                prev_checks = None
            if isinstance(prev_checks, list) and prev_checks:
                checks = [str(item) for item in prev_checks]
    _write_json(checks_path, checks)
```
Adjust the summary strings to say whether checks were preserved or regenerated.
- [ ] **Step 2:** Add a script test (same `_run_script` pattern): with a prior bundle whose `check_commands_path` file contains `["pytest tests/test_x.py -q"]`, the retry bundle's checks file preserves that list; without one, the fallback trivial checks are written.
- [ ] **Step 3:** Run the covering selectors; commit: `git commit -m "Preserve recovered design-gap retry check commands"`

---

### Task 8: Selector contract cleanup (subtractive prompt edits + one wiring fix)

**Files:**
- Modify: `workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md`
- Modify: `workflows/library/prompts/lisp_frontend_selector/select_next_work.md`
- Modify: `workflows/library/prompts/lisp_frontend_selector/review_done_design_delta.md`
- Modify: `workflows/library/lisp_frontend_selector.v214.yaml` (autonomous selector composite)

- [ ] **Step 1 (`select_next_design_delta_work.md`):**
  - Delete the "use target-design reasoning only to propose genuinely new bounded gaps" authorization and reword the `DRAFT_DESIGN_GAP` case to: `Return DRAFT_DESIGN_GAP only for a design gap listed as eligible in the manifest.` (The done-review path owns minting new gaps.)
  - Delete the baseline-design sentence (~:9-10, "Use the baseline design as a background contract...") — the step never injects the baseline.
  - Delete the "do not select refactoring twice in a row" rule (~:34-35) — unevaluable from the selector's inputs.
  - Delete `prerequisite_relation` from the example schemas (~:57,71) — the deterministic path owns prerequisite routing.
- [ ] **Step 2 (`select_next_work.md` + `review_done_design_delta.md`):** replace "work graph" phrasing with "selector manifest" (the actual injected artifact).
- [ ] **Step 3 (autonomous publisher):** in `workflows/library/lisp_frontend_selector.v214.yaml` find the `publish_lisp_frontend_selection_bundle.py` step (~:158-166) and add `--manifest-path` with the manifest artifact/input already available in that composite (grep the file for `manifest` to find the reference; if the composite genuinely has no manifest input, add one wired from the drain's `BuildBacklogManifest` output — check `workflows/examples/lisp_frontend_autonomous_drain.yaml` call site).
- [ ] **Step 4:** Loader smoke on both selector composites and both drains; run `python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q -k "selector or selection"`. Commit: `git commit -m "Align selector prompts with actual selection contracts"`

---

### Task 9: Step-back honesty and dead escalation value

**Files:**
- Modify: `workflows/library/prompts/workflow_step_back/diagnose_non_progress.md`
- Modify: `workflows/library/scripts/record_workflow_step_back_outcome.py:13-21`
- Modify: `workflows/library/scripts/evaluate_workflow_non_progress.py:15` (+ any use)
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml:375` area and `workflows/examples/non_progress_step_back_demo.yaml` (`TERMINAL_HUMAN_DECISION` arms)
- Test: `tests/test_workflow_non_progress_step_back_demo.py`

- [ ] **Step 1:** Shrink `ALLOWED_ACTIONS` to the actions the workflow enacts:
```python
ALLOWED_ACTIONS = {
    "FIX_WORKFLOW_MECHANICS",
    "CONTINUE_WITH_CURRENT_PLAN",
    "NEEDS_HUMAN_DECISION",
}
```
- [ ] **Step 2:** Rewrite the diagnosis prompt's action menu to those three, with honest semantics: `CONTINUE_WITH_CURRENT_PLAN` (the loop's own recovery machinery is the right responder), `FIX_WORKFLOW_MECHANICS` (the workflow itself is broken — ends the drain for repair), `NEEDS_HUMAN_DECISION` (a real external decision — ends the drain). Delete the four unenacted options and the "Prefer REDRAFT_PLAN or SPLIT_WORK_ITEM" sentence.
- [ ] **Step 3:** Delete `TERMINAL_HUMAN_DECISION` from `evaluate_workflow_non_progress.py`, from the drain YAML's allowed-enum/route arm (~:375), and its unreachable match arm in `non_progress_step_back_demo.yaml` (~:60,141).
- [ ] **Step 4:** Update `tests/test_workflow_non_progress_step_back_demo.py` if its demo diagnosis writer emits a removed action (check the demo YAML's deterministic writer); run:
```bash
python -m pytest tests/test_workflow_non_progress_step_back_demo.py tests/test_workflow_non_progress_recovery.py -q
```
This demo test executes a real workflow — it doubles as the orchestrator smoke check for this task.
- [ ] **Step 5:** Loader smoke on both YAMLs; commit: `git commit -m "Limit step-back diagnoses to enactable actions"`

---

### Task 10: Drain loops exhaust to BLOCKED instead of run failure

**Files:**
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml` (loop at ~:204)
- Modify: `workflows/examples/lisp_frontend_autonomous_drain.yaml` (loop at ~:121)
- Modify: `workflows/examples/neurips_steered_backlog_drain.yaml` (loop, `max_iterations: 240`)
- Modify: `workflows/library/neurips_backlog_implementation_phase.v214.yaml` (`ImplementationReviewLoop` ~:373)

- [ ] **Step 1:** Add to each of the three drain `repeat_until` blocks (after `max_iterations`):
```yaml
      on_exhausted:
        outputs:
          drain_status: BLOCKED
```
- [ ] **Step 2:** Add to the neurips `ImplementationReviewLoop`:
```yaml
      on_exhausted:
        outputs:
          review_decision: REVISE
```
(`REVISE` is already an allowed value; downstream `FinalizeImplementationPhaseOutputs` accepts COMPLETED+REVISE and the parent routes non-APPROVE away from `RecordCompletedItem` — Task 11 Step 3 makes that landing spot label itself honestly.)
- [ ] **Step 3:** Loader smoke on all four YAMLs (they are v2.14; `on_exhausted` needs ≥2.12). Commit: `git commit -m "Publish drain summaries on loop exhaustion instead of failing runs"`

---

### Task 11: neurips drain routing fixes

**Files:**
- Modify: `workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py` (~:222-229)
- Modify: `workflows/library/neurips_selected_backlog_item.v214.yaml` (`RecordSelectionRejected` ~:740, `RecordRoadmapBlocked` ~:795)
- Modify: `workflows/library/scripts/validate_neurips_backlog_gap_draft.py` (~:226)
- Modify: `workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml` (+ legacy `neurips_backlog_seeded_plan_phase.yaml` if present — check)
- Modify: `workflows/library/prompts/neurips_backlog_gap_drafter/draft_missing_item.md`
- Test: `tests/test_neurips_backlog_roadmap_gate.py`, `tests/test_neurips_steered_backlog_runtime.py`

- [ ] **Step 1 (gate DONE):** Change the status resolution to emit DONE for a genuinely empty backlog under `block` policy:
```python
    if eligible:
        gate_status = "ELIGIBLE"
    elif has_current_phase_item:
        gate_status = "BLOCKED"
    elif not all_items and policy["gap_policy"] == "block":
        gate_status = "DONE"
    elif policy["gap_policy"] == "draft_backlog_item":
        gate_status = "BACKLOG_GAP"
    else:
        gate_status = "BLOCKED"
```
Add a gate test: empty manifest (`items: []`, `invalid_items: []`) + `gap_policy: block` → `DONE`. Check existing tests for the empty+block case and flip if they assert BLOCKED.
- [ ] **Step 2 (record sync rejections):** In `RecordSelectionRejected`'s inline Python, add the run-state block recording (mirror `RecordRoadmapBlocked`'s subprocess call verbatim, passing the resolved `item_path`) and neutralize the hardcoded misdiagnosis strings: `"failed_stage": "selection_or_review"`, `"reason": "Selected item was rejected before completion (selection, sync, or review did not approve it)."`. Append `${inputs.run_state_path}` to the step's argv and adjust `sys.argv` indices.
- [ ] **Step 3 (delete dead step):** Delete the entire `RecordRoadmapBlocked` step (grep first to confirm zero `goto` references; the auditor found none).
- [ ] **Step 4 (validator):** In `validate_neurips_backlog_gap_draft.py` `main()`, change the except-handler to `return 0` after `_write_validation_failure(...)` (the INVALID bundle is the contract; downstream `ResolveItemSelection` already maps non-VALID to BLOCKED). Verify the gap_drafter workflow's output contract tolerates the INVALID bundle (grep its YAML for `draft_validation_status` enum).
- [ ] **Step 5 (findings carry-forward):** Copy the `ExtractOpenPlanFindings` step verbatim from `workflows/library/tracked_plan_phase.yaml:268-303` into the REVISE branch of the neurips seeded plan phase loop (v214, and legacy variant if it has the same loop), immediately before its `WriteRevisedPlanDecision`-equivalent step, keeping the `publishes: open_findings` block.
- [ ] **Step 6 (drafter prompt):** In `draft_missing_item.md` replace the pinned-phase lines (:12 "Do not advance to CDI, Phase 3, Phase 4, or Phase 5 work." and :19 "containing an allowed Phase 2 PDEBench phase from the gap request") with: `Use only roadmap phases the gap request's allowed_roadmap_phase_prefixes permit, and do not draft items in its disallowed phases.`
- [ ] **Step 7:** Verify:
```bash
python -m pytest tests/test_neurips_backlog_roadmap_gate.py tests/test_neurips_steered_backlog_runtime.py -q
```
plus loader smoke on the three touched neurips YAMLs. Commit: `git commit -m "Fix neurips drain completion, rejection recording, and gap-draft routing"`

---

### Task 12: Stop stamping `selector_blocked` on non-selector iterations

Recovery/step-back placeholder selections route through the `BLOCKED` arm that appends a `run_blocked --reason selector_blocked` event, polluting durable provenance.

**Files:**
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml` (BLOCKED arm `WriteBlocked` ~:939-967) and/or `workflows/library/scripts/update_lisp_frontend_run_state.py` (`run_blocked` handler)

- [ ] **Step 1 (investigate, bounded):** Trace how a recovery-placeholder iteration flows through `RouteSelection`'s BLOCKED arm and confirm whether `WriteBlocked` executes on iterations that ultimately CONTINUE (the audit found `run_blocked` events appended on every recovery/step-back iteration). Identify the artifact that distinguishes a genuine selector BLOCKED (the selection bundle's `pre_selection_route` or the placeholder's rationale field).
- [ ] **Step 2:** Apply the narrowest guard the trace supports. Preferred: in `update_lisp_frontend_run_state.py`'s `run_blocked` handler, read the `--selection-path` bundle and skip appending the event (still writing the drain-status file it owes) when the bundle marks a non-selector origin (e.g. `pre_selection_route` present and != `SELECT_NORMAL_WORK`, or the placeholder rationale marker found in Step 1).
- [ ] **Step 3:** Acceptance: a recovery iteration that resolves CONTINUE appends no `run_blocked` history event; a genuine selector BLOCKED still does. Encode both as a script-level test. Run the covering selectors; commit clean files: `git commit -m "Record selector_blocked provenance only for real selector blocks"`

---

### Task 13: Delete stale and orphaned surfaces

**Files:**
- Delete: `workflows/library/prompts/lisp_frontend_design_delta_work_item/revise_target_design_for_blocker.md`, `review_target_design_revision.md` (orphans; grep first to confirm still unreferenced by yaml/orc)
- Delete: `workflows/library/scripts/classify_lisp_frontend_implementation_blocker.py`, `workflows/library/scripts/detect_lisp_frontend_prior_blocked_design_gap.py` (orphans; confirm)
- Delete: `workflows/library/prompts/workflow_plan_review/` (orphan family; confirm)
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py` — delete `test_design_delta_blocker_revision_prompts_keep_roles_clear` (:5812) and remove the two deleted prompts from any other test's `prompt_paths` list (:5806 area), delete tests covering the two deleted scripts (grep by script name) — pre-dirty, no commit
- Modify: `workflows/library/prompts/lisp_frontend_implementation_phase/review_implementation.md` — delete the numerical-parity/physics boilerplate (~:55-67, keeping the validation-data-in-production kernel if it is not duplicated by another bullet), and drop the `## High` exact-header clause (~:93-95), keeping "group findings by severity"
- Modify: `workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/review_implementation.md` — same `## High` clause (~:59-61)
- Modify: `workflows/library/prompts/generic_run_watchdog/repair_run_failure.md` — replace `${inputs.state_root}/watch.json` and `${inputs.repair_result_target_path}` phrasing with references to the injected watch bundle ("the injected watch bundle records the evidence paths, target run id, and the repair result target path"); state which `recovery_action` pairs with terminal `PLAN_WRITTEN`
- Modify: `workflows/library/prompts/adjudication/evaluate_candidate.md` — change "Write strict JSON" to "Your entire stdout must be exactly one JSON object (no fences, no prose)"
- Modify: skill-noun prompts (`neurips_backlog_implementation_phase/implement_implementation.md`, `fix_implementation.md`; `major_project_stack/implement_plan.md`, `fix_implementation.md`, `revise_plan.md`, `review_implementation.md`; `generic_run_watchdog/repair_run_failure.md`) — replace `Use executing-plans` / `use receiving-code-review` / `use systematic-debugging` / "use the `managing-workflows` skill" with the behavioral contract each stands for (e.g. "Execute the plan task by task, verifying each step's expected result before moving on"; "Before disputing or implementing a review finding, verify it against the code"; "Diagnose the failure systematically before changing anything: reproduce it, locate the faulty component, and fix the root cause, not the symptom")
- Modify: `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml` — delete the never-published `design_revision_review_decision` artifact declaration (~:100-103) — pre-dirty, no commit

- [ ] **Step 1:** For each deletion, `grep -rn "<name>" workflows/ orchestrator/ tests/ docs/` first; delete only if the sole references are the file itself and wording-only tests (delete those too).
- [ ] **Step 2:** Apply the prompt modifications listed above.
- [ ] **Step 3:** `python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q -k "prompt or roles" && python -m pytest --collect-only tests/test_lisp_frontend_autonomous_drain_runtime.py -q | tail -2` (collection must succeed after test deletions).
- [ ] **Step 4:** Loader smoke on `workflows/examples/generic_run_watchdog.yaml`, `workflows/examples/adjudicated_provider_demo.yaml`, `workflows/library/neurips_backlog_implementation_phase.v214.yaml`. Commit clean files: `git commit -m "Remove orphaned recovery prompts, dead scripts, and stale prompt boilerplate"`

---

### Task 14: Full verification sweep and report

- [ ] **Step 1:** Loader smoke over every YAML touched by any task:
```bash
python3 - <<'EOF'
from pathlib import Path
from orchestrator.loader import WorkflowLoader
paths = [
    "workflows/examples/lisp_frontend_design_delta_drain.yaml",
    "workflows/examples/lisp_frontend_autonomous_drain.yaml",
    "workflows/examples/neurips_steered_backlog_drain.yaml",
    "workflows/examples/non_progress_step_back_demo.yaml",
    "workflows/examples/generic_run_watchdog.yaml",
    "workflows/examples/adjudicated_provider_demo.yaml",
    "workflows/library/lisp_frontend_design_delta_work_item.v214.yaml",
    "workflows/library/lisp_frontend_design_delta_done_review.v214.yaml",
    "workflows/library/lisp_frontend_selector.v214.yaml",
    "workflows/library/lisp_frontend_design_delta_selector.v214.yaml",
    "workflows/library/lisp_frontend_implementation_phase.v214.yaml",
    "workflows/library/lisp_frontend_design_delta_implementation_phase.v214.yaml",
    "workflows/library/lisp_frontend_plan_phase.v214.yaml",
    "workflows/library/lisp_frontend_design_delta_plan_phase.v214.yaml",
    "workflows/library/neurips_selected_backlog_item.v214.yaml",
    "workflows/library/neurips_backlog_implementation_phase.v214.yaml",
    "workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml",
]
failed = False
for p in paths:
    loader = WorkflowLoader(Path.cwd())
    try:
        loader.load_bundle(Path(p))
        errs = loader.error_count()
        print(("OK  " if errs == 0 else f"ERR {errs} "), p)
        failed = failed or errs != 0
    except Exception as e:
        print("EXC ", p, type(e).__name__, str(e)[:120]); failed = True
raise SystemExit(1 if failed else 0)
EOF
```
- [ ] **Step 2:** Test modules:
```bash
python -m pytest tests/test_workflow_non_progress_recovery.py tests/test_workflow_non_progress_step_back_demo.py tests/test_neurips_backlog_roadmap_gate.py tests/test_workflow_lisp_projection_dual_run.py -q
python -m pytest tests/test_neurips_steered_backlog_runtime.py -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q
```
Compare failure sets against the Task 0 baseline: no new failures allowed.
- [ ] **Step 3:** Write the final report: per task — what changed, verification evidence, which edits landed in pre-dirty files and remain uncommitted, and the deferred list from the plan header.
