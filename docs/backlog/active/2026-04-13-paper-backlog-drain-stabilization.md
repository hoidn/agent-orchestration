# Backlog Item: Paper Backlog Drain Stabilization

Current disposition: **historical paper-drain proposal; external run state unverified.**

Repository YAML mechanics are historical. External paper-project scope and verification/environment prerequisites remain; this reconciliation did not inspect that checkout or establish run completion.

Gate retained: External work/run selection remains separate; do not launch or declare done.
This is a documentation disposition, not evidence of implementation completion
or authorization for new execution, spend, prompt edits or runtime work.
Current owners: [lisp workflow drafting guide](../../lisp_workflow_drafting_guide.md), [workflow lisp evaluated execution](../../design/workflow_lisp_evaluated_execution.md), [cli](../../../specs/cli.md).
[Backlog status inventory](../README.md).

Original proposal / historical checkpoint begins below. Its original status,
commands, measurements and tense are preserved; they do not override the current
scope notice.


- Status: active
- Created on: 2026-04-13
- Plan: `docs/plans/2026-04-13-paper-backlog-drain-stabilization-plan.md`

## Scope
Implement the paper backlog drain stabilization plan.

The current drain workflow became brittle after the one-shot `selection -> stack` adapter was expanded into a repeated drain loop. The follow-up work should keep the selector as the only judgment-heavy provider step, keep loop mechanics and ledger updates in workflow YAML, and use the generic backlog item stack's declared outputs instead of reading child workflow private state.

## Required Work
- Finish or verify provider `output_bundle` Output Contract injection, including resolved runtime paths in composed prompts.
- Add a focused runtime regression for the `repeat_until + output_bundle + match + call + ledger` shape.
- Refactor the paper drain workflow so `RouteSelectedBacklogItem` exports the selected item outcome through match outputs.
- Move ledger recording after the match statement and record from `RouteSelectedBacklogItem` artifacts.
- Tighten the paper backlog selector prompt so it relies on the injected Output Contract instead of duplicating path and field details.
- Run the local and paper-repo verification commands listed in the plan.

## Success Criteria
- The plan is implemented and checked off.
- The paper drain workflow dry-runs from `/home/ollie/Documents/ptychopinnpaper2`.
- A debug run's selector prompt includes the concrete `output_bundle` path for the current run and iteration.
- The drain workflow records processed items from the generic item stack's declared `item_outcome` output, not from direct reads of child state files.
