# Backlog Item: Design Review Transformation-Necessity Experiment

- Status: active
- Created on: 2026-04-13
- Plan: none yet

## Scope
Evaluate whether adding an explicit transformation-necessity/null-path instruction to design-review prompts improves workflow review quality across general design-plan-implement stacks.

Candidate prompt block:

```text
Reject designs that include a materially outcome-affecting transformation, semantic adapter, inherited default, or helper behavior without first justifying why the step should exist at all.
For each such step, compare against the null path: skip the step, use the original artifact semantics, or use a simpler existing path. A design is not ready if it tunes parameters, thresholds, or tolerances while leaving the step's necessity unjustified.
```

The motivation is a Fig. 5 revision-study review case where reviewers needed to catch unjustified metric and fine-registration defaults, including the possibility that an inherited transformation was unnecessary or counterproductive. The line may improve recall by forcing reviewers to test whether material actions should exist at all, but it may also add prompt weight, over-broaden findings, or duplicate the existing rejection rules.

## Desired Outcome
Produce an evidence-backed recommendation:

- keep the transformation-necessity/null-path block in canonical design-review prompts
- narrow or reword it
- restrict it to scientific/metrics-heavy review prompts
- or remove it and rely on the existing convention/helper/semantic-assumption rejection rules

## Experiment Design
Compare review behavior with and without the candidate line on a small set of existing design-review cases.

At minimum, include:

- one revision-study metrics design with alignment/registration/evaluation choices
- one non-metrics design-plan-implement review
- one small/simple design where extra prompt weight could cause over-review

For each case, record:

- whether the review catches semantically material but implicit assumptions
- whether findings are specific enough to drive a useful design revision
- whether the line creates redundant or noisy findings
- whether the line changes decision severity in a justified way

## Non-Goals
Do not treat one successful review sample as enough evidence.
Do not add prompt text that hard-codes Fig. 5, registration, metrics, or study-specific terminology into general prompts.
Do not add tests that assert literal prompt wording.

## Success Criteria
This item is satisfied when a follow-on plan or experiment report identifies the evaluated cases, summarizes outcomes, and recommends whether the candidate line should be retained, narrowed, scoped, or removed.
