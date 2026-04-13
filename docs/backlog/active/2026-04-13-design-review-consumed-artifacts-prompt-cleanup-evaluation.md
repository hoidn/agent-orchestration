# Backlog Item: Evaluate Design Review Consumed-Artifacts Prompt Cleanup

- Status: active
- Created on: 2026-04-13
- Plan: none yet

## Scope
Evaluate whether the consumed-artifacts prompt cleanup improves design-review behavior in generic design-plan-implement and revision-study workflows.

The cleanup removed duplicated "read these artifacts before acting" wording from design-review prompts and kept the semantic guidance that matters:

- use the `Consumed Artifacts` section as the authoritative input list
- treat runtime artifact names such as `approved_design` as workflow plumbing, not lifecycle proof
- use open-findings artifacts for carried-forward versus new finding reconciliation
- consult `docs/index.md` first when repository documentation is needed

## Desired Outcome
Produce an evidence-backed recommendation:

- keep the cleaned-up wording
- restore more explicit artifact-read instructions
- narrow the change to only revision-study prompts
- or move some guidance into workflow injection text instead of prompt files

## Experiment Design
Compare review behavior before and after the cleanup on a small set of review prompts or prompt audits.

At minimum, include:

- one revision-study design review with open findings
- one generic design-plan-implement design review with open findings
- one review where repository docs/specs affect the decision

For each case, record:

- whether the agent reads the consumed artifacts and open-findings ledger correctly
- whether the agent preserves the intended fresh-review-then-reconcile behavior
- whether the docs/index guidance is followed when relevant without conflicting with consumed-artifact authority
- whether the prompt becomes shorter/clearer without reducing review quality

## Non-Goals
Do not add tests that assert literal prompt text.
Do not broaden the prompt cleanup into unrelated review policy changes.

## Success Criteria
This item is satisfied when a follow-on note or plan compares at least the cases above and recommends whether to keep, revise, or revert the cleanup.
