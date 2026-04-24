# Artifact Surface Prompt Edits Plan

**Date:** 2026-04-23

## Goal

Apply the subtractive prompt changes that the simulation supported so major-project and generic design-plan-implement prompts stop promoting derived report/evidence surfaces into tranche-contract scope by default.

## Files

- Modify: `workflows/library/prompts/major_project_stack/draft_big_design.md`
- Modify: `workflows/library/prompts/major_project_stack/review_big_design.md`
- Modify: `workflows/library/prompts/major_project_stack/revise_big_design.md`
- Modify: `workflows/library/prompts/design_plan_impl_stack_v2_call/draft_plan.md`
- Modify: `workflows/library/prompts/design_plan_impl_stack_v2_call/review_implementation.md`

## Edits

1. Narrow big-design contract language from broad `durable artifacts` wording to maintained contracts, stable consumed outputs, and externally consumed persistent artifacts.
2. State explicitly that generated reports, summaries, projections, and review evidence are derived by default unless they are authoritative, stable downstream inputs, or explicit user-facing deliverables.
3. Mirror that subtractive rule in the big-design revise prompt so revision loops do not reintroduce the old framing.
4. Narrow generic planning language so generated evidence artifacts do not become current-scope work by default.
5. Narrow implementation review so derived evidence artifacts are not blocking by themselves unless the approved design or plan made them authoritative, consumed, or user-facing.

## Verification

- `git diff --check` on the edited prompt files and this plan
- `pytest tests/test_major_project_workflows.py -q`
- one major-project dry-run smoke
- one generic design/plan/impl dry-run smoke
