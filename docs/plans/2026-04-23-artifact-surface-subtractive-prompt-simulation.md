# Artifact-Surface Subtractive Prompt Simulation

**Date:** 2026-04-23

## Candidate Change

Simulate the effect of the proposed subtractive edits to:

- `workflows/library/prompts/major_project_stack/draft_big_design.md`
- `workflows/library/prompts/major_project_stack/review_big_design.md`
- `workflows/library/prompts/design_plan_impl_stack_v2_call/draft_plan.md`
- `workflows/library/prompts/design_plan_impl_stack_v2_call/review_implementation.md`

The intended behavior change is:

- reduce default promotion of generated reports, summaries, projections, and review evidence into tranche-contract surfaces
- keep authoritative source-of-truth artifacts, stable consumed outputs, and user-facing deliverables visible
- make implementation review less likely to block on derived-artifact drift when the real contract is elsewhere

## Scope And Blast Radius

Prompt consumer scope at simulation time:

- `draft_big_design.md` and `review_big_design.md` are consumed by `workflows/library/tracked_big_design_phase.yaml`
- `draft_plan.md` is consumed by `workflows/library/tracked_plan_phase.yaml`
- `review_implementation.md` is consumed by `workflows/library/design_plan_impl_implementation_phase.yaml`

That means the major-project big-design edits are narrow, but the plan and implementation-review edits affect generic design-plan-implement users beyond the EasySpin tranche drain.

One material asymmetry exists in the proposal as drafted: `major_project_stack/revise_big_design.md` still contains the old broad artifact-contract wording. If only the drafted files change, revise-loop behavior can reintroduce the same artifact-heavy framing during design revision.

## Scenario 1: T24 Full ENDOR / salt Expansion

**Type:** target case where the change should help

**Current expected behavior**

- The design and plan elevate a large evidence surface into tranche scope: authored catalogs plus generated reports, examples, docs updates, ledger closure, and execution-summary artifacts.
- Implementation review treats the report bundle as part of tranche closure, so drift in generated report artifacts can keep the tranche open even after the underlying runtime behavior is correct.
- Late iterations are likely to continue finding report-gate and closure-surface problems rather than core ENDOR / `salt` defects.

**Proposed expected behavior**

- The design is more likely to classify parity catalogs, benchmark catalogs, runtime records, and stable docs as authoritative, while treating generated report bundles and summaries as derived unless they are a stable downstream input or explicit user-facing deliverable.
- The plan is more likely to focus current-scope work on maintained source-of-truth surfaces and the generation/check path for derived reports, instead of making every generated artifact independently approval-critical.
- Implementation review is more likely to classify a bad report-artifact check as an invalid gate or derived-evidence defect rather than a core tranche blocker, unless that report is itself the authoritative contract.

**Regression risk**

- Moderate if the edit is applied incompletely: a revise pass could still push the design back toward broad artifact-contract language because `revise_big_design.md` still has the old wording.
- Low risk of hiding real issues, because the maintained catalogs, runtime rows, and stable docs remain clearly in-scope under the proposed wording.

**Recommendation**

- The direction is good.
- The exact draft is incomplete because it does not update `revise_big_design.md`.

## Scenario 2: T25 Full curry And Magnetometry Expansion

**Type:** hard case where the change may not be sufficient

**Current expected behavior**

- Review correctly finds real contract defects: missing crystal-control ownership, unfrozen case-family descriptor grammar, vague explicit-output bundle contract, and an ambiguous `Opt.Spins` legality rule.
- Those are behavior and contract problems, not report-surface problems.

**Proposed expected behavior**

- Review still finds the same high-value issues, because the subtractive changes do not weaken checks on public contracts, ownership boundaries, stable consumed outputs, or descriptor grammar.
- The design may become slightly cleaner by not feeling pressure to over-specify report bundles or generated evidence roots unless they are actually authoritative.

**Regression risk**

- Low.
- The proposal does not remove the review prompt's ability to reject vague or under-specified public/API/contract decisions.

**Recommendation**

- Good sign. The change appears to reduce process gravity without blinding the reviewer to the kind of design gap that actually matters for T25.

## Scenario 3: Workflow Dashboard Observability

**Type:** generic shared-prompt consumer

**Current expected behavior**

- The dashboard work is already centered on stable contracts: CLI surface, read-only dashboard behavior, safe file resolution, projection logic, and tested server routes.
- The generic plan prompt can still encourage broad tasking around docs and artifacts, but the artifact surface is mostly justified because the specs and CLI are maintained sources of truth.

**Proposed expected behavior**

- The plan remains materially the same for production code, CLI/spec updates, and security/read-only contracts.
- The plan is slightly less likely to treat generated or incidental evidence artifacts as first-class current-scope work unless a downstream consumer depends on them.
- Implementation review is less likely to block on derived summaries or projections if the maintained contract and server behavior are already correct.

**Regression risk**

- Low.
- The proposed wording still keeps maintained data/contracts and stable consumed outputs in scope, which covers the important dashboard surfaces.

**Recommendation**

- Acceptable blast radius for generic design-plan-implement users.

## Scenario 4: Major-Project Demo Repo Docs Baseline

**Type:** small/simple case where the change could add overhead or loosen too much

**Current expected behavior**

- A tiny major-project tranche can be pushed toward boilerplate about artifact roots, generated outputs, and report surfaces even when the work is intentionally minimal.

**Proposed expected behavior**

- The design stays small and self-contained.
- The prompt is less likely to manufacture unnecessary artifact-contract prose around a minimal docs-baseline tranche.

**Regression risk**

- Very low.
- The proposal removes noise rather than adding it.

**Recommendation**

- Helpful for small tranches.

## Comparison Summary

| Scenario | Current expected behavior | Proposed expected behavior | Regression risk | Recommendation |
| --- | --- | --- | --- | --- |
| T24 ENDOR / `salt` | Late-stage churn on generated reports and report-gate closure | More pressure to keep authoritative surfaces narrow and derived surfaces derived | Moderate if revise prompt stays old; otherwise low | revise proposal, then adopt |
| T25 `curry` | Review catches real contract gaps | Same real gaps stay visible; less artifact noise | Low | adopt |
| Dashboard workflow | Strong contract focus already | Mostly unchanged, with less incidental artifact pressure | Low | adopt |
| Demo docs baseline | Prompt can over-specify artifacts | Simpler, cleaner design output | Very low | adopt |

## Overall Recommendation

**Decision:** `REVISE_AND_RESIMULATE`

The subtractive direction is correct, and the expected behavior is better than the current prompt set on the motivating T24 case without obvious regression on T25 or a generic shared-prompt consumer.

I would not adopt the exact draft as written because it is asymmetric:

- `draft_big_design.md` and `review_big_design.md` would move toward the narrower artifact-surface model
- but `revise_big_design.md` would still tell the reviser to treat source code, tools, durable artifacts, and curated data broadly as tranche-contract surfaces

That asymmetry is likely to reintroduce the old behavior during design revision loops.

If the proposal is revised to include the same subtractive classification rule in `workflows/library/prompts/major_project_stack/revise_big_design.md`, the expected recommendation becomes:

**`ADOPT_NARROWLY`**

meaning:

- adopt the narrowed big-design draft/review/revise wording in the major-project stack
- adopt the generic `draft_plan.md` and `review_implementation.md` wording because the simulated regression risk appears low
- do not assume this fixes revision-study or follow-on prompt families, which use different prompt files

## Follow-Up

- Mirror the subtractive artifact-surface rule into `workflows/library/prompts/major_project_stack/revise_big_design.md`
- Then re-run a short confirmation simulation on the same four scenarios
