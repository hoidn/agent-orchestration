# Claim-Support Big-Design Prompt Experiment

## Status

Active backlog item. Do not apply the prompt edits until this experiment is intentionally selected.

## Context

The major-project workflow has been useful for EasySpin PyTorch-port tranches, but recent runs showed a recurring failure mode: late implementation reviews had to reconstruct which material claims the design and plan were trying to support. A proposed fix to add deterministic "contract gates" was rejected as too brittle and too likely to turn judgment into bookkeeping.

The current proposal is narrower: test whether major-project big-design prompts should ask for proportionate evidence expectations for the main material claims a tranche depends on.

Reference documents:

- `docs/plans/2026-04-16-claim-support-guidance-prompt-proposal.md`
- `docs/plans/2026-04-16-claim-support-guidance-simulation-report.md`

## Candidate Scope

Only these prompt files are in scope for the first experiment:

- `workflows/library/prompts/major_project_stack/draft_big_design.md`
- `workflows/library/prompts/major_project_stack/revise_big_design.md`
- `workflows/library/prompts/major_project_stack/review_big_design.md`

Explicitly out of scope for the first experiment:

- shared generic plan, execution, fix, and implementation-review prompts under `workflows/library/prompts/design_plan_impl_stack_v2_call/`
- revision-study prompts
- backlog-item prompts
- workflow YAML or artifact contract changes

The shared generic prompts are used outside the major-project stack, including backlog-item workflows, so changing them requires a separate proposal and simulation.

## Candidate Prompt Change

Draft and revise big-design prompts would add guidance like:

```markdown
When the tranche changes public behavior, claims about supported behavior or API surface, performance claims, durable contracts, scientific conclusions, or other outcome-affecting project claims, briefly state what evidence would make the main material claims acceptable. Put this in the design's verification, acceptance, or equivalent existing section. Keep this proportionate: usually prose or a short list, not an exhaustive matrix. Use behavior tests, public API probes, architecture inspection, benchmarks with correctness anchors, generated freshness checks, manual scientific inspection, or explicit deferral as appropriate. Do not create evidence rows for routine file edits or bookkeeping unless they affect a material claim.
```

The big-design review prompt would reject designs that make material public behavior, supported-behavior/API-surface, performance, durable-contract, or scientific claims without credible and proportionate evidence expectations, while also saying not to require exhaustive evidence maps or routine bookkeeping findings.

## Experiment Plan

1. Select one future major-project tranche or a controlled major-project fixture.
2. Run or simulate the tranche with current prompts and record expected design/review behavior.
3. Apply the big-design-only candidate prompt edits in a test branch or clearly scoped commit.
4. Run or simulate the same tranche with the candidate prompts.
5. Compare outcomes using the success and failure signals below.
6. Decide one of:
   - adopt big-design-only prompt edits;
   - revise wording and resimulate;
   - reject the change;
   - write a separate proposal for shared generic plan/implementation prompts.

## Success Signals

- Design reviews catch unsupported behavior/API-surface, benchmark, durable-contract, or scientific-claim gaps earlier.
- Designs express the evidence for main material claims compactly in existing verification or acceptance sections.
- Plans carry those expectations through existing generic plan-review language without new prompt edits.
- Implementation reviews find fewer late surprises caused by ambiguous design claims.
- Review findings remain focused on behavior, API semantics, architecture, maintainability, and material verification.

## Failure Signals

- Designs grow new mandatory-looking evidence tables or row-by-row claim maps.
- Reviewers start nitpicking evidence wording instead of material design quality.
- Small major-project tranches get more ceremony without better decisions.
- Architecture, API semantics, or implementation maintainability receive less attention.
- Agents start creating deterministic validators, ledgers, or generated reports by default even when they are not natural evidence.

## Notes

The simulation report currently recommends `ADOPT_BIG_DESIGN_ONLY`, but that recommendation is based on mental simulation. This backlog item exists because prompt changes are behaviorally hard to evaluate after they influence real workflow artifacts. Treat this as an experiment with explicit observation criteria, not as an already-approved prompt patch.

