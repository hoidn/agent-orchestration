# Claim-Support Guidance Prompt Proposal

> **For review-only simulation:** This is a proposal, not an approved implementation plan. Do not apply the prompt changes from this file before an independent simulation/review decides whether they are likely to improve workflow outcomes.

**Goal:** Evaluate a small prompt-guidance change that makes the major-project big-design phase reason about material claims and their supporting evidence without adding a mandatory evidence table, deterministic validator convention, or EasySpin-specific bookkeeping process.

**Context:** Recent major-project workflow runs caught real defects, but several late implementation-review cycles became dominated by closure ledgers, report fields, and proof bookkeeping. A prior proposal to add "contract gates" was rejected as too brittle and too likely to miss the forest. This proposal tests a more general claim-support framing.

---

## Hypothesis

The workflow will work better if major-project big-design prompts ask agents to identify and preserve credible evidence for material claims, while keeping that guidance proportionate and explicitly avoiding mandatory evidence matrices.

Expected improvement:

- design review catches unsupported behavior, weak benchmark claims, weak deferrals, and misleading docs/spec claims earlier;
- downstream generic plan/review prompts already have enough "material design requirements become concrete work" language to preserve credible claim evidence when the design states it clearly;
- implementation review sees clearer design intent without changing shared implementation-review prompts for every workflow user.

Possible regression:

- agents may create new bureaucratic "evidence" sections;
- reviewers may nitpick missing evidence rows;
- design iterations may increase without reducing implementation iterations;
- architecture and implementation quality may get crowded out by meta-evidence language.

The independent reviewer should treat both outcomes as plausible.

## Proposed Scope

Apply the first experiment only to the major-project big-design prompt family:

- `workflows/library/prompts/major_project_stack/draft_big_design.md`
- `workflows/library/prompts/major_project_stack/revise_big_design.md`
- `workflows/library/prompts/major_project_stack/review_big_design.md`

Do not edit shared generic plan or implementation prompts in the first experiment. In this repo, `workflows/library/prompts/design_plan_impl_stack_v2_call/*` is used through shared phases by both the major-project tranche stack and the backlog-item stack, so changing those prompts would not be a major-project-only experiment.

Do not apply this proposal to revision-study prompts, backlog-item prompts, shared generic plan/implementation prompts, or workflow YAML in the first experiment.

## Non-Goals

- Do not add a mandatory `Acceptance Evidence` table.
- Do not add a deterministic-validator convention.
- Do not add EasySpin-specific language.
- Do not require exhaustive claim enumeration.
- Do not make docs/report completeness a default blocker.
- Do not add prompt wording tests.
- Do not change workflow control flow or artifact contracts in this proposal.
- Do not edit shared generic plan or implementation prompts unless a separate follow-on proposal explicitly broadens scope to every stack that consumes them.

## Proposed Prompt Edits

These are intentionally small. The wording is candidate wording for simulation, not approved final text.

### 1. Draft Big Design

File: `workflows/library/prompts/major_project_stack/draft_big_design.md`

Add after the existing paragraph that ends with `verification strategy with visible checks and reviewable artifacts`:

```markdown
When the tranche changes public behavior, claims about supported behavior or API surface, performance claims, durable contracts, scientific conclusions, or other outcome-affecting project claims, briefly state what evidence would make the main material claims acceptable. Put this in the design's verification, acceptance, or equivalent existing section. Keep this proportionate: usually prose or a short list, not an exhaustive matrix. Use behavior tests, public API probes, architecture inspection, benchmarks with correctness anchors, generated freshness checks, manual scientific inspection, or explicit deferral as appropriate. Do not create evidence rows for routine file edits or bookkeeping unless they affect a material claim.
```

Apply the same addition to `workflows/library/prompts/major_project_stack/revise_big_design.md`, adapted from "state" to "preserve or update" if needed:

```markdown
When revising a design that changes public behavior, claims about supported behavior or API surface, performance claims, durable contracts, scientific conclusions, or other outcome-affecting project claims, preserve or update what evidence would make the main material claims acceptable. Put this in the design's verification, acceptance, or equivalent existing section. Keep this proportionate: usually prose or a short list, not an exhaustive matrix. Use behavior tests, public API probes, architecture inspection, benchmarks with correctness anchors, generated freshness checks, manual scientific inspection, or explicit deferral as appropriate. Do not create evidence rows for routine file edits or bookkeeping unless they affect a material claim.
```

### 2. Review Big Design

File: `workflows/library/prompts/major_project_stack/review_big_design.md`

Add one rejection bullet near the existing verification and hidden-work bullets:

```markdown
- make material public behavior, claims about supported behavior or API surface, performance, durable-contract, or scientific claims without credible and proportionate evidence expectations, or with evidence that would not actually support the claim
```

Add one guardrail sentence before `Approve when...`:

```markdown
Do not require an exhaustive evidence map or table. Review whether the design's evidence expectations are credible for its main material claims; avoid findings about routine bookkeeping unless the omission could mislead downstream work, weaken reproducibility, or make an unsupported claim appear supported.
```

## Non-Actionable Follow-On Sketch: Shared Generic Plan/Implementation Prompts

If the independent simulation concludes that big-design-only guidance is not enough, write a separate proposal for the shared generic plan and implementation prompts. That follow-on must honestly broaden the scope to all users of `tracked_plan_phase.yaml` and `design_plan_impl_implementation_phase.yaml`, including backlog-item workflows.

Candidate follow-on edits, not part of the first experiment:

- `workflows/library/prompts/design_plan_impl_stack_v2_call/draft_plan.md`: if the design names evidence needed for material claims, include plan steps that produce that evidence or explicitly replace it with stronger evidence.
- `workflows/library/prompts/design_plan_impl_stack_v2_call/review_plan.md`: check whether material design claims are paired with evidence expectations or explicitly flag the missing evidence expectation as a design gap; do not silently build a plan on unsupported claims.
- `workflows/library/prompts/design_plan_impl_stack_v2_call/implement_plan.md`: in the execution report's Verification section, connect checks to the material claims they support when the plan identifies such claims.
- `workflows/library/prompts/design_plan_impl_stack_v2_call/fix_implementation.md`: when fixing review findings, preserve or update verification evidence for the material claims affected by the fix.
- `workflows/library/prompts/design_plan_impl_stack_v2_call/review_implementation.md`: review whether delivered work provides credible evidence for material claims made by the design and plan; treat missing docs, reports, generated artifacts, or bookkeeping as blocking only when the gap affects a material claim, reproducibility, downstream use, or a required boundary for supported behavior or API surface.

The follow-on simulation must include both a major-project tranche and a generic backlog-item workflow, because the prompt targets are shared.

## Simulation Protocol For Impartial Reviewer

Run two mental simulations, one with current prompts and one with the proposed edits. Do not assume the edits help.

Use at least three scenarios:

1. A port-closure tranche like EasySpin T16, where public selected behavior, unsupported modes, docs/spec claims about supported behavior or API surface, and prior-tranche leftovers are all in scope.
2. A performance tranche like EasySpin T17, where benchmark claims need correctness anchors and reduced precision must not silently weaken defaults.
3. A small local feature that changes one implementation unit and has ordinary tests, where a heavy evidence model would be overhead.

For each scenario, compare:

- design artifact length and specificity;
- number and quality of design-review findings;
- whether design review catches claim/evidence issues earlier;
- whether unchanged generic plan review remains focused on executable work and still carries the design's material evidence expectations when they are present;
- whether unchanged implementation review finds fewer, more, or the same number of new classes of missing evidence;
- whether reviewers start nitpicking evidence language;
- whether behavior/API/maintainability review gets crowded out;
- whether the likely total review iterations go down, stay flat, or increase.

The reviewer should write a short simulation report with one row or paragraph per scenario:

- current expected behavior;
- proposed big-design-only expected behavior;
- regression risk;
- recommendation: `ADOPT_BIG_DESIGN_ONLY`, `REVISE_AND_RESIMULATE`, `REJECT`, or `BROADEN_TO_SHARED_PROMPTS_WITH_SEPARATE_PROPOSAL`.

## Decision Criteria

Recommend adopting the edits only if the simulation predicts all of the following:

- improved handling of material claims about supported behavior or API surface, behavior, benchmark, or scientific claims;
- no strong tendency toward mandatory evidence tables or row-by-row evidence bureaucracy;
- no likely reduction in attention to architecture, API semantics, implementation correctness, or maintainability;
- plausible reduction in late implementation-review surprise findings;
- small expected prompt-size and artifact-size increase.

Recommend rejecting or revising the proposal if the simulation predicts any of the following:

- reviewers will use the guidance as a new checklist;
- designs will grow significantly without better decisions;
- agents will replace concrete tests or architecture decisions with vague "evidence" prose;
- small tranches will carry major-project ceremony;
- deterministic validators or ledgers will be generated by default even when not natural evidence.

## Initial Recommendation To Be Tested

Do not add a new formal workflow section or artifact. Add only the small prompt guidance above, and only to the major-project big-design path first.

The next simulation should evaluate only these revised big-design prompt candidates. Shared generic plan, execution, fix, and implementation-review prompt changes remain out of scope until a separate proposal evaluates their impact on both major-project and backlog-item workflows.

If the independent simulation is mixed, prefer a narrower review-only change:

```markdown
When reviewing, ask whether material claims are supported by credible evidence. Do not require an evidence table, exhaustive claim map, or extra bookkeeping for routine work.
```

This narrower fallback may capture most of the benefit with less risk of design bloat.
