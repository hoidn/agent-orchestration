# Claim-Support Guidance Simulation Report

## Inputs Reviewed

- Proposal: `docs/plans/2026-04-16-claim-support-guidance-prompt-proposal.md`
- Current big-design prompts:
  - `workflows/library/prompts/major_project_stack/draft_big_design.md`
  - `workflows/library/prompts/major_project_stack/revise_big_design.md`
  - `workflows/library/prompts/major_project_stack/review_big_design.md`
- Current shared downstream prompts:
  - `workflows/library/prompts/design_plan_impl_stack_v2_call/draft_plan.md`
  - `workflows/library/prompts/design_plan_impl_stack_v2_call/review_plan.md`
  - `workflows/library/prompts/design_plan_impl_stack_v2_call/review_implementation.md`
- EasySpin examples:
  - `docs/plans/pytorch-port-roadmap/T16-remaining-api-expansion-design.md`
  - `docs/plans/pytorch-port-roadmap/T16-remaining-api-expansion-plan.md`
  - `artifacts/review/pytorch-port-roadmap/T16-remaining-api-expansion-implementation-review.json`
  - `docs/plans/pytorch-port-roadmap/T17-performance-optimization-design.md`
  - `docs/plans/pytorch-port-roadmap/T17-performance-optimization-plan.md`
  - `artifacts/review/pytorch-port-roadmap/T17-performance-optimization-implementation-review.json`

## Recommendation

`ADOPT_BIG_DESIGN_ONLY`

The revised proposal is a reasonable first experiment. It keeps the scope limited to the major-project big-design prompt family, avoids changing shared generic plan and implementation prompts, and replaces the earlier exhaustive-sounding `each material claim` wording with `main material claims`. It also directs the guidance into the existing verification, acceptance, or equivalent design section, which should reduce the chance of new evidence-table bureaucracy.

This change should not be expected to solve downstream implementation failures by itself. It is best treated as a low-risk design-phase improvement that can be evaluated in real runs before deciding whether a separate proposal should broaden to shared generic plan, execution, fix, and implementation-review prompts.

## Scenario Simulations

### 1. EasySpin T16-Like Port Closure

Current expected behavior:

The current big-design prompt already forces self-contained tranche context, roadmap constraints, package layout, cross-tranche reuse, implementation architecture, documentation impact, and verification strategy. That was enough to surface at least one meaningful design-stage issue in T16: package-wide closure had to cover the full T12-T16 denominator, not only the selected T11 rows. However, later implementation review still had to reason through support claims and closure evidence in detail, including public selected behavior, unsupported modes, blocked-record ledgers, and package-wide docs/spec statements.

Proposed big-design-only expected behavior:

The revised guidance should improve the design-stage treatment of T16-like work. A drafter is more likely to state what evidence supports the main claims the tranche depends on: selected APIs are actually supported, valid unsupported modes are represented as deliberate boundaries, package rows are closed for a reviewable reason, and docs/spec claims do not overstate implementation status. Because the new wording says `main material claims` and points to the existing verification or acceptance section, the design can express this as a compact acceptance strategy rather than a row-by-row evidence ledger.

Regression risk:

Low to moderate. T16-like closure work naturally needs some ledger detail, so reviewers may still lean into bookkeeping. The revised wording reduces that risk enough for a first experiment, but real runs should watch whether design reviews start blocking on routine report fields or docs churn rather than support semantics.

Recommendation:

`ADOPT_BIG_DESIGN_ONLY`

This is the strongest positive scenario for the proposal.

### 2. EasySpin T17-Like Performance And Precision Tranche

Current expected behavior:

The current T17 design already states the important evidence concepts: benchmark coverage, correctness anchors, MATLAB/PyTorch baseline comparison, reduced-precision constraints, default `float64`/`complex128` preservation, no silent fallback, and evidence-gated production optimization. The implementation review later found serious issues anyway: benchmark coverage was too narrow, correctness gates did not enforce the approved contracts, MATLAB baseline support was a placeholder, invalid selectors silently succeeded, and the report did not make an evidence-based optimization decision.

Proposed big-design-only expected behavior:

The revised guidance may sharpen the design review around the main performance and precision claims: what benchmark coverage is representative, what correctness anchors are needed before speed claims count, and what evidence is required before reduced precision or GPU/device support can be claimed. It probably would not prevent all T17 failures, because several were downstream implementation or validator defects rather than missing design intent. The benefit is earlier clarity, not complete enforcement.

Regression risk:

Low. Performance tranches already require evidence, and the revised wording avoids a mandatory evidence matrix. The main remaining risk is over-crediting the design-phase change for failures that need later plan/execution/review prompt or validator improvements.

Recommendation:

`ADOPT_BIG_DESIGN_ONLY`

Adopt for design clarity, while explicitly preserving the proposal's deferred follow-on path for shared downstream prompts if real runs still show T17-like late evidence failures.

### 3. Small Major-Project Tranche With One Implementation Unit

Current expected behavior:

The current major-project big-design prompt is already fairly heavy. For a small tranche, it relies on "where relevant" language, the design template's "omit irrelevant optional sections" instruction, and the prompt's distinction between design-level and plan-level detail. A reasonable agent can produce a compact design with one implementation unit and ordinary tests, but there is still some risk of over-structuring because the major-project stack is built for durable, multi-tranche work.

Proposed big-design-only expected behavior:

The revised proposal should add little overhead. A small design can satisfy it with a sentence in verification or acceptance, such as ordinary behavior tests covering the one public behavior change. Because the text no longer asks for evidence for every material claim, it is less likely to turn a small tranche into a claim ledger.

Regression risk:

Low to moderate. Some agents may still create an "Evidence" subsection because the word appears in the prompt, but the instruction to use the existing verification or acceptance section should make that less likely.

Recommendation:

`ADOPT_BIG_DESIGN_ONLY`

The small-tranche risk is acceptable for a major-project-only experiment.

## Decision Criteria Check

| Criterion | Result | Notes |
| --- | --- | --- |
| Improved handling of material claims about supported behavior or API surface, behavior, benchmark, or scientific claims | Met | Strongest for T16-like support/closure claims; useful but less decisive for T17-like performance claims. |
| No strong tendency toward mandatory evidence tables or row-by-row evidence bureaucracy | Mostly met | The revised `main material claims` wording and existing-section placement are important mitigations. Watch real runs for review drift. |
| No likely reduction in attention to architecture, API semantics, implementation correctness, or maintainability | Mostly met | The addition is small and remains in the big-design phase. It should complement existing architecture checks rather than replace them. |
| Plausible reduction in late implementation-review surprise findings | Partially met | Likely reduces late surprises caused by unclear design evidence. It will not fix implementation validators or runner behavior by itself. |
| Small expected prompt-size and artifact-size increase | Met | The prompt additions are short and should not require new design sections. |

## Adoption Notes

Apply only the revised big-design prompt candidates from the proposal:

- `workflows/library/prompts/major_project_stack/draft_big_design.md`
- `workflows/library/prompts/major_project_stack/revise_big_design.md`
- `workflows/library/prompts/major_project_stack/review_big_design.md`

Do not edit shared generic plan, execution, fix, or implementation-review prompts as part of this experiment. If later real runs still show T17-like downstream evidence failures, write a separate proposal that honestly broadens the scope to every stack using `tracked_plan_phase.yaml` and `design_plan_impl_implementation_phase.yaml`, including backlog-item workflows.

## Suggested Success Signals For Real Runs

- Design reviews catch unsupported support/API, benchmark, or scientific claims earlier without adding broad evidence tables.
- Plans carry the design's main evidence expectations as concrete work through existing generic plan-review language.
- Implementation review finds fewer surprises caused by ambiguous design claims.
- Review findings remain focused on behavior, API semantics, architecture, maintainability, and material verification instead of routine docs/report bookkeeping.
