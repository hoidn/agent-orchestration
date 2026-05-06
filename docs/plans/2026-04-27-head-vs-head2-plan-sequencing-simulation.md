# HEAD vs HEAD^^ Plan Sequencing Prompt Simulation

## Inputs And Exclusions

Compared versions:

- New: `HEAD` = `c50d9a3 Order major-project fixes by dependencies`
- Old: `HEAD^^` = `67c8740 Clarify design prompt phase boundary`

Compared files:

- `workflows/library/prompts/major_project_stack/draft_plan.md`
- `workflows/library/prompts/major_project_stack/review_plan.md`
- `workflows/library/prompts/major_project_stack/revise_plan.md`
- `workflows/library/prompts/major_project_stack/fix_implementation.md`

Evidence used:

- Current T26 approved design and plan in `/home/ollie/Documents/EasySpin/docs/plans/pytorch-port-roadmap/`
- Current T26 implementation review text visible in `artifacts/work/pytorch-port-roadmap/T26-full-chili-slow-motion-solver-expansion-execution-report.md` and the live review stream
- Repo plan template `docs/plans/templates/plan_template.md`, especially `Key Invariants`, `Implementation Steps`, and `Verification Strategy`
- Prompt diffs from `HEAD^^..HEAD`

Excluded:

- Provider hidden reasoning.
- Any claim that a single prompt line deterministically changes provider behavior.
- Current uncommitted prompt changes outside `HEAD`.

## Compared Versions

`HEAD^^` already required plans to account for material design requirements, sequence prerequisites before dependent work, and reject broad undifferentiated plans. It did not require the plan to name central required results before the task list, nor did it explicitly tell review to reject dependent work scheduled before the result it relies on.

`HEAD` adds:

- Drafting: before `Implementation Steps`, include `Key Invariants` for central behavior/interface/data/integration/user-visible results, and order dependent tasks after the task and check that establish the result.
- Review: reject plans that put dependent work too early.
- Plan revision: preserve or add the same `Key Invariants` ordering.
- Implementation fix: address findings in dependency order.

## Scenario Setup

Scenario A: T26 `chili` CPU float64 closure.

- Target issue: exact public solver path and `outputs.spec` parity are the central required result.
- Dependent work: catalog/report/docs/workflow acceptance updates.

Scenario B: a hard but non-numerical tranche that changes a public API and generated client docs.

- Target issue: API behavior and compatibility must be implemented before docs and generated client snapshots.

Scenario C: a small local bugfix with one function and one test.

- Target issue: avoid adding process overhead where no meaningful dependency chain exists.

## Evidence Ledger

- Observed: Current T26 plan has correct units, but treats exact solver replacement, catalog migration, report migration, workflow acceptance, and docs as broad sibling tasks.
- Observed: Current T26 implementation review says a narrow chunk-plan issue was fixed, while the main exact-solver/parity closure remains open.
- Specified: `HEAD` drafting prompt uses `Key Invariants`, a section already present in the repo plan template.
- Specified: `HEAD` review prompt explicitly rejects dependent work scheduled before the behavior/interface/data/integration/user-visible result it relies on.
- Inferred: Provider behavior changes probabilistically; the new prompt increases the chance of a critical-path plan but does not guarantee it.

## Deterministic Workflow Delta

No deterministic DSL routing changes are in `HEAD^^..HEAD`. The change is provider-judgment only:

- plan drafting prompt content changes
- plan review prompt content changes
- plan revision prompt content changes
- implementation fix prompt content changes

The workflow still accepts the same plan/review decisions.

## Simulated Event Log

### Scenario A, Old Version: `HEAD^^`

1. Draft plan consumes the approved T26 design.
   - Output: a broad implementation plan with units for contracts, runtime policy, preflight, exact solver, reports, workflow/docs, and verification.
   - Rationale: prompt requires accounting for all material design requirements and sequencing prerequisites, but does not require naming the central required result first.
   - Confidence: high, because this matches the observed T26 plan.

2. Plan review consumes design and plan.
   - Output: `APPROVE`.
   - Rationale: plan is complete, scoped to the design, has boundaries, and has verification. Review prompt lacks a direct test for dependent work scheduled around central required results.
   - Confidence: high, because this matches the observed T26 review.

3. Implementation starts.
   - Output: agent works on tractable surrounding issues; review finds core preview solver/parity still open.
   - Rationale: broad sibling tasks permit visible progress without first closing exact solver parity.
   - Confidence: medium-high, because this matches current T26 behavior.

Terminal expectation: several implementation iterations; risk of local churn before escalation.

### Scenario A, New Version: `HEAD`

1. Draft plan consumes the approved T26 design.
   - Expected output: a `Key Invariants` section naming at least:
     - public CPU `chili` rows do not use preview numerics
     - selected `outputs.spec` parity passes reviewed comparison
     - dependent contract/report/docs/workflow updates describe the proven public behavior
   - Expected task order: exact solver path and parity check before closure-bundle/catalog/docs updates.
   - Confidence: medium. The prompt points that way, but the design is still large and may tempt broad inventories.

2. Plan review consumes design and plan.
   - If the plan still treats solver replacement and report/docs migration as siblings, expected output is `REVISE`.
   - Required change: put dependent tasks after the task and check establishing exact solver parity.
   - Confidence: medium-high. The new review sentence directly names the failure pattern.

3. Implementation starts from revised/approved plan.
   - Expected output: first implementation work targets exact solver path and parity checks, or a narrow blocker is surfaced earlier.
   - Confidence: medium. The new `fix_implementation` line helps keep review fixes in dependency order, but implementation can still choose shallow fixes if reviews are not explicit.

Terminal expectation: fewer peripheral fix cycles before either solver closure or a clear local failure.

### Scenario B, Old Version: `HEAD^^`

1. Draft plan accounts for API implementation, generated client update, docs, and migration tests.
2. Plan may schedule docs/client snapshots alongside or before API behavior stabilization.
3. Review may approve if all work is present and verification is plausible.

Terminal expectation: implementation review may later find generated artifacts are stale or describe unproven API behavior.

### Scenario B, New Version: `HEAD`

1. Draft plan names key invariant: API behavior and compatibility shape are established.
2. Implementation steps put API behavior and compatibility tests before generated clients/docs.
3. Review rejects if generated clients/docs precede the API result and check they depend on.

Terminal expectation: better ordering, without project-specific assumptions.

### Scenario C, Old Version: `HEAD^^`

1. Draft plan produces a small scope, one implementation step, one test.
2. Review approves.

Terminal expectation: low overhead.

### Scenario C, New Version: `HEAD`

1. Draft prompt says include `Key Invariants` only when there is a central behavior/interface/data/integration/user-visible result.
2. For a simple bugfix, this may add one short invariant or be omitted if not useful.
3. Review is unlikely to reject only because the section is absent unless dependent work is actually misordered.

Terminal expectation: small overhead risk; acceptable if reviewers do not turn `Key Invariants` into a mandatory template for all tasks.

## Decision Rationale

`HEAD` addresses the observed T26 failure mode better than `HEAD^^` because it gives both drafting and review a concrete structural hook: required results before dependent work. It also extends the same idea into plan revision and implementation fixing, which matters when a plan is approved but later review exposes a dependency-order problem.

It does not fully solve the problem. If the design is too large, a provider may still write a large `Key Invariants` section and then keep a broad task list. Review quality remains decisive.

## Comparison

Expected benefit:

- Moves critical-path ordering issues from implementation review into plan review.
- Reduces the chance of artifact/docs/report churn before behavior is real.
- Uses existing template language instead of inventing new workflow jargon.
- Generalizes to API, data, integration, and user-visible outcomes.

Expected cost:

- Slightly more plan text for nontrivial work.
- Reviewers may over-apply `Key Invariants` as a mandatory section for simple tasks unless the wording stays conditional.
- The phrase "user-visible result" is broad; acceptable, but review should focus on concrete dependency ordering.

## Assumptions And Falsifiers

Assumptions:

- Plan drafters will place `Key Invariants` before `Implementation Steps` when the central result is obvious.
- Reviewers will use the new sentence to reject sibling-task plans that hide dependency order.
- Implementation reviewers will recognize dependency order from the plan instead of treating each finding as equally local.

Falsifiers:

- A new T26-style plan under `HEAD` still lists core behavior and dependent artifacts as siblings and gets approved.
- Review findings start complaining about missing `Key Invariants` in simple plans with no dependency chain.
- Implementation fixes keep patching dependent artifacts before the behavior they describe.

## Regression Risks

- Low risk for small tasks if the conditional wording is respected.
- Medium risk for large tranches: `Key Invariants` may become another verbose checklist unless review keeps it tied to actual dependency order.
- Medium risk that plan review still approves broad plans unless it compares `Key Invariants` to `Implementation Steps` concretely.

## Recommendation

`ADOPT_NARROWLY`.

Keep the `HEAD` change. It is small, uses existing template structure, and directly targets the observed plan failure without EasySpin-specific nouns.

Do not broaden it into a larger planning template yet. First observe one or two new major-project plans and check whether the `Key Invariants` section actually changes task order. If it becomes boilerplate, revise the wording to say the section may be one or two bullets and should be omitted when it does not change task order.
