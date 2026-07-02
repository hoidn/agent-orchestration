# Drain Recovery-Loop Mechanics Repairs

Status: in progress
Created: 2026-07-02
Scope: four small mechanics repairs preventing the repeated-block / stalled-recovery
class observed in the 2026-07-02 runtime-native drain runs (`20260702T085610Z-c0q0gx`,
`20260702T121602Z-fpq40u`).

Executed inline (not subagent-driven): each fix is a small, single-surface change
in a tree shared with a live drain run; inline execution keeps staging under
direct control. The live run consumes these scripts on its next iteration;
no workflow YAML is modified.

## Observed failure class

1. The same gap cycled blocked → `GAP_DESIGN_REVISION_REQUIRED` → revise → re-block
   up to four times with the same failure fingerprint before a human intervened.
   Nothing deterministic counts completed revise→retry→re-block cycles.
2. Revisions rejected by retry-side architecture validation
   (`recovered_retry_unavailable`) still emit `gap_design_revision` history events,
   which the progress projection counts as accepted changes — masking the
   non-progress triggers that should have fired.
3. The recovered-retry work item re-plans from the revised architecture only; the
   prior attempt's blocking evidence reaches the planner only if the reviser
   manually transcribes it into the plan.
4. Implementers read a plan's file list as a prohibition and report BLOCKED rather
   than widening a slice generically ("the approved plan forbids" + enumerated
   files = implied fence). The recovered phasectx plan had to add a bespoke
   "behavioral, not file-count-based" paragraph to undo this.

## Fixes

### Fix 1 — revision-cycle ratchet (detect script only, no YAML)

`detect_lisp_frontend_blocked_design_gap_recovery.py`:

- compute per-gap `revision_cycles`: completed revise→…→re-block cycles from run-state
  history (a revision event for the item followed later by a blocked event for the item);
- include `revision_cycles` in the recovery payload (`blocked-recovery.json` is injected
  into the drain-level classifier as content, so the classifier sees the count with no
  prompt change);
- when `revision_cycles >= 3`, return the BLOCKED payload with reason
  `local_recovery_exhausted` — the run stops honestly for external review instead of
  burning further provider cycles. Threshold 3 is deliberately above the point where the
  classifier historically self-escalated (cycle 2), so the deterministic stop is a
  backstop, not a substitute for classification.

### Fix 2 — rejected revisions are not progress (projection script only)

`project_lisp_frontend_progress_signals.py`: a `gap_design_revision` /
`design_revision` / `plan_revision` event whose next same-item history event is
`recovered_retry_unavailable` is projected with `accepted_change: false`,
`outcome: blocked`, and a stable fingerprint derived from the retry-block reason.
Repeated rejected revisions then trip `same_blocker_repeated` /
`no_accepted_change_streak` instead of resetting them.

### Fix 3 — prior-attempt evidence reaches the retry planner (materializer only)

`materialize_lisp_frontend_recovered_design_gap_draft.py`: append the blocked
progress report content (from the recovery bundle's `progress_report_path`) to
`recovered-work-item-context.md`. The retry work item's plan phase already consumes
the work-item context, so the planner sees the prior attempt's evidence without new
plumbing or prompt text.

### Fix 4 — file lists are orientation, not fences (implement prompts)

Both `implement_plan.md` prompts (generic + design-delta): the blocking rule
binds only to what the plan explicitly forbids; a plan's file/module list is
orientation, not a prohibition. One-sentence change per prompt; removes the
implied constraint that caused honest BLOCKED stalls.

## Non-goals

- No reordering of the drain YAML revise/validate/record steps (considered:
  validating revised docs before recording the revision event; rejected as a
  live-run-risky reorder for the same observable effect Fix 2 achieves in the
  projection).
- No new recovery routes, reasons enums, or prompt taxonomy.
- No per-gap iteration budgets beyond the cycle ratchet.

## Verification

- Unit tests per fix in `tests/test_lisp_frontend_autonomous_drain_runtime.py`
  (Fixes 1–3); `pytest --collect-only` on the module.
- No literal prompt-text assertions (repo rule) — Fix 4 is verified by loader
  smoke on the affected workflow YAMLs.
- Loader smoke (`WorkflowLoader.load_bundle`) on the drain, work-item, and
  implementation-phase YAMLs after all fixes.
