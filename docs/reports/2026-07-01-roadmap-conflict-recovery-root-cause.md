# Roadmap Conflict Recovery Root Cause

Status: diagnostic report
Created: 2026-07-01
Scope: lisp-native drain blocked-gap recovery behavior, roadmap-conflict handling, gap-design revision behavior, and the distinction between one-off gap correction and general workflow mechanics.

## Summary

The current roadmap conflict is not primarily a compiler problem, and it is not best fixed by adding another project-specific exception to the active gap. The immediate blocked gap contains a stale implementation assumption: a selected-item stdlib route is expected to reuse an existing hidden/private `run_state_path` compatibility lane, but the current checkout no longer exposes a usable `.orc` binding for that lane on that route. Satisfying the plan as written would reintroduce the run-state carrier/bridge plumbing that the target design is trying to retire.

The general workflow failure is broader: when an implementation reports a roadmap conflict caused by a stale or impossible assumption in a gap architecture/plan, the recovery path can revise the gap by preserving the blocked requirement and adding more checks, evidence, or compatibility wording around it. That turns a blocker into process churn. The revision should instead remove, narrow, split, or explicitly block the causal assumption.

The simplest general fix is to change the blocked-gap revision contract so that a revision must address the blocker-causing assumption directly. It should not be accepted if it keeps the same impossible path and merely adds verification around it.

## Current Run State

Active run inspected:

- Run id: `f10b031d837d4267a65ee3f161988f74`
- Workflow: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
- Persisted status at inspection: `running`
- Current persisted repeat iteration: `DrainLispFrontendWork`, iteration `2`

The workflow and watchdog tmux sessions were stopped before further implementation work, so the persisted state may still read `running` until the runtime/monitor observes process death or the run is explicitly resumed/restarted.

Relevant active gap:

- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/design-gaps/workflow-lisp-design-delta-work-item-private-phasectx-boundary/`

Relevant blocked recovery decision:

- `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R39/drain/iterations/2/blocked-recovery-decision.json`
- Route: `GAP_DESIGN_REVISION_REQUIRED`
- Reason: `implementation_architecture_under_scoped`

The classifier decision was reasonable: the target design remained coherent, but the selected gap architecture/plan was under-scoped or stale relative to the actual code route.

## Immediate Incident

The implementation worker blocked with `roadmap_conflict`. Its reported reason was that the approved slice required using an already-existing hidden/private `run_state_path` lane on the selected-item stdlib route, but that lane is not available in the current checkout outside the direct owner route.

The gap architecture and plan still treated the compatibility write to `state/run_state.json` as part of the current private-`PhaseCtx` boundary slice. In particular, the plan required preserving or restoring:

- `blocked_recovery_reason` in `state/run_state.json`
- `blocked_recovery_summary` in `state/run_state.json`
- an existing hidden/private `run_state_path` compatibility lane
- a blocked-recovery compatibility merge as part of the selected-item route

That conflicts with the direction of the target design, which is to keep internal workflow composition typed and carrier-free, while pushing legacy files/views/bridges to declared boundaries or retiring them.

## Why The One-Off Fix Is Not Enough

A one-off fix for this gap would be to edit the gap plan and delete the `state/run_state.json` blocked-recovery write from this private-context slice. That is directionally correct for this incident, but it is not the general fix.

The general problem is that the workflow can keep doing this on future gaps:

1. A plan contains a stale implementation assumption.
2. Implementation proves the assumption is false.
3. The blocker is classified as gap-design revision required.
4. The revision agent preserves the stale assumption and adds more verification or explanatory language.
5. The next implementation attempt blocks again, now with more process around the same impossible path.

That pattern can happen with any stale mechanism, not just `run_state_path` or compatibility bridges.

## General Root Cause

The recovery contract distinguishes target-design revision, gap-design revision, prerequisite gaps, and terminal blockers, but it does not strongly require the gap-design revision to retire the exact assumption that caused the block.

The current revision prompt says to make the smallest principled change that resolves the blocker. That is too underspecified when the consumed gap plan contains strong stale wording. A model can interpret "resolve" as "preserve the requirement but add more proof, tests, metadata, or bridge wording." In the current incident, that is exactly the wrong move: the plan should stop requiring the missing lane, not prove it harder.

Consistency classification:

- `stale_duplicate`: the gap architecture/plan preserved legacy run-state compatibility requirements after the target direction moved toward carrier retirement.
- `over_specific_instruction`: the gap required a specific hidden route (`run_state_path` lane) rather than the higher-level behavior the slice actually needed.
- `semantic_conflict`: the target design prefers carrier-free selected-item composition, while the gap plan required restoring a compatibility carrier effect.
- `missing_recovery_path`: the recovery loop had a way to revise the gap, but no firm rule that the revision must remove, narrow, split, or block the causal assumption.

## Correct General Behavior

When an implementation blocks because the approved plan requires a route, binding, artifact, API, or state transition that does not exist or conflicts with the target design, recovery should do one of four things:

1. Remove the requirement if it is not necessary for the target-design slice.
2. Narrow the requirement to the actual behavior needed.
3. Split it into a separate prerequisite or follow-up gap if it is real but belongs to another slice.
4. Return `BLOCKED` if the allowed editable surface cannot resolve it.

The revision should not:

- preserve the same blocked path and add more evidence around it;
- turn a stale compatibility requirement into a stronger acceptance condition;
- convert implementation scaffolding into target behavior;
- widen public or hidden contracts just to make the old plan pass;
- add project-specific exception text when the real issue is stale assumption handling.

## Minimal General Fix

The smallest general fix is a replacement in the blocked-gap revision prompt:

```text
Make the smallest principled design change that resolves the blocker by
removing, narrowing, or splitting the stale assumption that caused it. Do not
preserve a blocked requirement by adding more evidence, checks, or wording
around the same failed path.
```

This is intentionally general. It does not name runtime, bridges, Workflow Lisp, Design Delta, or `run_state_path`. It applies to any gap where the implementation proves that the approved plan is trying to execute an invalid path.

The next-smallest optional hardening is a revision-report field or validator that asks the reviser to name the blocker-causing assumption and how it was handled:

```json
{
  "blocked_assumption": "",
  "resolution": "removed | narrowed | split | blocked",
  "same_failed_path_preserved": false
}
```

That would be stronger, but it is more machinery. The prompt replacement is the minimal general fix.

## Why This Is Better Than More Evidence Requirements

The current failure is not due to insufficient proof. It is due to preserving the wrong requirement. More verification can make the workflow slower and more confident about the wrong path.

A useful recovery revision should make the next implementation attempt simpler and more aligned with the target design. If a revision makes the plan longer while keeping the same impossible route, it is probably worsening the situation.

In this incident, adding checks that prove `state/run_state.json` is updated would push the worker toward rebuilding compatibility plumbing. A better revision removes that requirement from the private-context slice and, if needed, creates a separate boundary-retirement question.

## Current Local Edits At Time Of Report

Before this report was written, two uncommitted edits had already been started:

- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/design-gaps/workflow-lisp-design-delta-work-item-private-phasectx-boundary/execution_plan.md`
  - Symptom-level edit that starts narrowing this specific gap away from `state/run_state.json` preservation.
  - This is not the general fix by itself.

- `workflows/library/prompts/lisp_frontend_design_delta_work_item/revise_prior_blocked_design_gap.md`
  - General prompt edit replacing the vague "smallest principled design change" instruction with a rule to remove, narrow, or split the stale assumption that caused the blocker.
  - This is the intended minimal general fix, pending review.

The active workflow sessions were stopped before proceeding further so the workflow would not spend another implementation attempt on the stale plan.

## Recommended Next Steps

1. Decide whether to keep the general prompt replacement.
2. Either revert or complete the one-off gap-plan edit so it consistently matches the general rule.
3. Run a narrow workflow dry-run or prompt-contract check after any prompt/YAML changes.
4. Relaunch or resume the workflow only after the consumed gap plan no longer asks the worker to preserve the same missing route.

The main principle should be: a recovery revision is successful only if it changes the causal assumption that made the implementation block. If it preserves that assumption and adds process around it, the workflow is still off track.

## Follow-Up Reconciliation

The prompt replacement was kept because it is the general fix: future blocked-gap revisions must remove, narrow, or split the stale assumption that caused the block instead of preserving the failed path with more checks.

The active gap plan was then completed in the split direction. Its goal, architecture, task, and acceptance sections now agree that the private-`PhaseCtx` selected-item slice must stay carrier-free and must not require `blocked_recovery_reason` or `blocked_recovery_summary` to be merged into `state/run_state.json`. If a live legacy consumer still needs those JSON fields, that is a separate boundary/bridge-retirement slice, not a prerequisite for this private-context gap.

The checked runtime evidence was aligned with that split:

- selected-item smoke tests still require typed blocked-recovery outputs;
- those tests now assert that the YAML-era blocked-recovery fields are absent from `state/run_state.json`;
- the resume-plumbing manifest no longer falsely marks `transitions.resource.drain_run_state` as `RETIRED`; it records `BLOCKED` until the bridge-backed drain-run-state resource is actually removed or moved to a separate declared boundary slice.

Verification performed after reconciliation:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py --collect-only -q
python -m pytest tests/test_workflow_lisp_transition_authoring.py::test_transition_authoring_report_passes_for_checked_design_delta_family tests/test_workflow_lisp_transition_authoring.py::test_transition_authoring_report_records_imported_finalize_selected_item_transition_origins -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_resume_plumbing_retirement_report_artifact tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_resume_plumbing_retirement_report_records_drain_run_state_bridge_as_checked_compatibility tests/test_workflow_lisp_build_artifacts.py::test_design_delta_work_item_direct_entry_phase_context_binding_uses_runtime_bootstrap_defaults tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_call_work_item_boundary_projection_records_imported_selected_item_context_bindings tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_selected_item_stdlib_keeps_run_state_bridge_private tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_parent_drain_runtime_fixture_mirror_stays_aligned_after_r5_cleanup -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_work_item_candidate_smokes_complete_and_blocked_recovery_routes tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_parent_call_work_item_smokes_complete_and_blocked_recovery_routes tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_work_item_candidate_smokes_terminal_blocked_route tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_parent_call_work_item_smokes_terminal_blocked_route -q
git diff --check
```

All listed checks passed after the reconciliation.
