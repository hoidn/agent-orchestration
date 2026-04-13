# Backlog Item: Compare Design Review Prompt Families for Generic Use

- Status: active
- Created on: 2026-04-13
- Plan: none yet

## Scope
Experimentally compare the two current design-review prompt families and recommend which wording should be the default for generic design-plan-implement workflows.

Prompt families to compare:

- `workflows/library/prompts/design_plan_impl_stack_v2_call/review_design.md`
- `workflows/library/prompts/revision_study_stack/review_design.md`

The generic prompt has stronger carried-forward finding mechanics and explicit scope classifications. The revision-study prompt has stronger domain-neutral repo-drift language and clearer handling of workflow-plumbing artifact names such as `approved_design`. Both now include the transformation-necessity/null-path check.

## Desired Outcome
Produce an evidence-backed recommendation:

- keep the generic prompt as the default and backport only selected revision-study wording
- make the revision-study prompt the base for generic use after removing study-specific language
- merge the best parts into a shared canonical design-review prompt
- or keep separate prompts with explicit guidance for when each is appropriate

## Experiment Design
Run both prompt families against the same small set of design-review cases, using the same consumed artifacts and output contract shape where possible.

At minimum, include:

- one revision-study metrics design with alignment, data-contract, and metric-policy choices
- one generic design-plan-implement design with architecture or API-contract consequences
- one small/simple design where an over-aggressive prompt could generate noisy findings
- one design with carried-forward open findings that require `RESOLVED` / `STILL_OPEN` / `SUPERSEDED` reconciliation

For each case, record:

- decision and high/medium finding counts
- whether findings are specific, actionable, and grounded in file evidence
- whether the reviewer catches semantically material but unnecessary or unjustified choices
- whether prior findings are reconciled correctly rather than mechanically preserved
- whether scope classification is useful or too specialized for the workflow
- whether repo-spec, architecture, and data-contract conflicts are caught when relevant
- whether the prompt produces noisy findings or blocks implementation on out-of-scope cleanup

## Non-Goals
Do not decide the canonical prompt from a single Fig. 5 revision-study sample.
Do not add prompt-text snapshot tests.
Do not hard-code revision-study, metrics, registration, or Fig. 5 terminology into a generic design-review prompt.
Do not merge prompt families until there is enough evidence that the merged prompt improves behavior outside the revision-study case.

## Related Work
See `docs/backlog/active/2026-04-13-design-review-audit-line-experiment.md` for the narrower experiment on the transformation-necessity/null-path block.
See `docs/backlog/active/2026-04-13-design-review-consumed-artifacts-prompt-cleanup-evaluation.md` for the narrower consumed-artifacts wording cleanup evaluation.

## Success Criteria
This item is satisfied when a follow-on plan or experiment report compares both prompt families on the cases above and recommends whether to keep, merge, or specialize the prompts for generic design-plan-implement use.
