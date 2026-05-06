# Implementation Dependency Order Prompt Simulation

## Inputs And Exclusions

Compared prompt state:

- Base: `be0cf01 Tighten major project plan sequencing prompts`
- Candidate: current working tree edits to:
  - `workflows/library/prompts/major_project_stack/revise_plan.md`
  - `workflows/library/prompts/major_project_stack/fix_implementation.md`

Evidence used:

- Current T26 plan: `/home/ollie/Documents/EasySpin/docs/plans/pytorch-port-roadmap/T26-full-chili-slow-motion-solver-expansion-plan.md`
- Current T26 execution report: `/home/ollie/Documents/EasySpin/artifacts/work/pytorch-port-roadmap/T26-full-chili-slow-motion-solver-expansion-execution-report.md`
- Current T26 implementation review: `/home/ollie/Documents/EasySpin/artifacts/review/pytorch-port-roadmap/T26-full-chili-slow-motion-solver-expansion-implementation-review.json`
- Current major-project prompt files in this repo.

Excluded:

- Provider hidden reasoning and any future live workflow outputs after this simulation started.
- Literal prompt-wording tests, because repo policy rejects tests that assert prompt phrasing.

## Compared Versions

Base behavior:

- Plan draft/review prompts ask for `Key Invariants` and reject plans that schedule dependent work too early.
- Plan revision prompt does not repeat the `Key Invariants` dependency-order rule.
- Implementation fix prompt says to prioritize high-severity issues, then current-scope work, then follow-up work, but does not explicitly say to fix dependency roots before dependent artifacts.

Candidate behavior:

- Plan revision prompt preserves or adds `Key Invariants` when task order is revised.
- Implementation fix prompt says: "Address review findings in dependency order. Fix the required behavior, interface, data shape, integration, or user-visible result before updating work that depends on it."

## Scenario Setup

Scenario A: T26 implementation has a broad approved plan. The current review says non-anchor public `chili` rows still execute preview solver code, while reports/catalogs overclaim closure.

Scenario B: A small single-file behavior fix has one failing test and no downstream publication or integration surface.

Scenario C: A plan review asks for reordering after finding that a migration task is scheduled before the data-shape change it needs.

## Evidence Ledger

- Observed: T26 plan explicitly names Task 4 as replacement of public preview numerics with the exact slow-motion solver path.
- Observed: Current execution report completed benchmark/catalog/report expansion while residual risks still mention limited exact-oracle coverage and promoted-row smoke behavior.
- Observed: Current implementation review has two high findings: public non-anchor rows still execute preview solver logic, and closure catalogs/reports overclaim denominator closure without required parity and representative-scale evidence.
- Inferred: The fix agent is likely to choose a narrower local fix from the latest review unless the prompt pushes it toward the earliest dependency root.

## Deterministic Workflow Delta

No DSL or runtime behavior changes. The workflow still routes through the same provider steps, review decisions, loop limits, artifact paths, and output contracts.

Only provider judgment changes.

## Simulated Event Log

### Scenario A, Base

1. Fix implementation provider reads plan, execution report, and review.
2. It sees high findings H-1 and H-2.
3. The existing priority list says to fix high-severity correctness or contract issues first, then complete current-scope work.
4. Because H-2 is a high contract/reporting issue and may look easier than replacing the solver, the provider may update catalogs/reports/tests to reduce overclaim wording or add benchmark coverage.
5. Review likely still returns `REVISE`, because H-1 remains: public non-anchor rows still use preview solver behavior.
6. Outcome: partial progress, but high churn risk remains.

Confidence: medium-high, because this resembles the observed T26 pattern.

### Scenario A, Candidate

1. Fix implementation provider reads the same artifacts.
2. It sees H-1 is the behavior root: public non-anchor rows execute the wrong solver path.
3. It sees H-2 depends on H-1: reports and catalogs should not claim closure until the runtime behavior and evidence exist.
4. The new instruction tells it to address review findings in dependency order.
5. Likely local action shifts toward either replacing the non-anchor solver path or demoting/marking rows so dependent closure artifacts cannot overclaim.
6. Review likely still may return `REVISE` if exact solver replacement is too hard, but the next revision should be more diagnostic: either real runtime progress or clear evidence that the approved implementation path is not closing locally.

Confidence: medium. The instruction cannot make a hard solver implementation easy, but it should reduce artifact-first patches.

### Scenario B, Base

1. Fix implementation provider reads a simple review finding.
2. It fixes the direct behavior and updates the execution report.
3. No meaningful difference.

Confidence: high.

### Scenario B, Candidate

1. The dependency-order instruction is satisfied by fixing the direct behavior first.
2. No extra section or process artifact is required.
3. No expected overhead beyond one sentence of prompt context.

Confidence: high.

### Scenario C, Base

1. Plan revision provider reads a review finding that migration order is unsafe.
2. It may reorder tasks locally, but it is not reminded to preserve or add `Key Invariants`.
3. The revised plan may still be accepted if it looks coherent, even if the dependency root is implicit.

Confidence: medium.

### Scenario C, Candidate

1. Plan revision provider reads the same finding.
2. It preserves or adds `Key Invariants` and states the result that downstream migration depends on.
3. The revised `Implementation Steps` can be reviewed against that invariant.
4. Review has a clearer hook to reject if dependent work remains too early.

Confidence: medium-high.

## Decision Rationale

The candidate edit is useful because it applies the dependency-order idea at the two places where the base prompt set was weakest:

- plan revision, after review has already found sequencing problems
- implementation fix, after review has already found dependency-related defects

It avoids workflow-role leakage. It does not mention iterations, cycles, routing, DSL decisions, or escalation. It only tells the current provider step how to order its local work.

## Comparison

Expected improvements:

- Dependent artifacts, reports, docs, migrations, or cleanup are less likely to be patched before the behavior/interface/data/integration they rely on.
- Plan revisions should keep the `Key Invariants` hook instead of dropping it after first draft.
- Implementation fixes should focus more naturally on root behavior before dependent surfaces.

Limits:

- This does not solve implementation work that is genuinely too large or scientifically hard.
- It does not force the implementation provider to slice or escalate; review/workflow still owns those decisions.
- It may not prevent all artifact churn when a review finding itself is framed around artifacts rather than the underlying behavior.

Expected T26 effect:

- Better than base, but not guaranteed to close T26. The likely benefit is fewer fixes that only make reports/catalogs internally consistent while runtime behavior remains wrong.

## Assumptions And Falsifiers

Assumptions:

- Providers read and follow the added prompt lines.
- The plan contains enough order information for "dependent work" to be interpretable.
- Reviews continue to identify behavior-root findings when dependent artifacts overclaim.

Falsifiers:

- A future run still repeatedly updates only dependent artifacts after review explicitly identifies an earlier behavior/root issue.
- Plan revisions delete or ignore `Key Invariants`.
- Review findings are written so artifact defects look independent from their underlying behavior dependency.

## Regression Risks

- Minor risk of over-focusing on order when truly independent high-severity findings can be fixed in parallel by one provider. The wording says "depends on it," so independent issues should remain unaffected.
- Minor risk that "Key Invariants" becomes boilerplate. This is already bounded by "when the work has a central behavior, interface, data shape, integration, or user-visible result."
- No deterministic workflow risk, because no YAML, routing, or artifact contracts changed.

## Recommendation

ADOPT_NARROWLY.

Keep the edit in the major-project prompt family. Do not broaden it to all generic prompt families until there is evidence that non-major workflows show the same dependency-order failure mode.
