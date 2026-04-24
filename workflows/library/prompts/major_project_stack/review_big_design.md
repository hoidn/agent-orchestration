<task>
Review the candidate design in a code-review stance. Findings first. Look for bugs, risks, missing tests, bad assumptions, hidden work, architectural drift, and downstream failure modes. Use the notes below as additional required checks, not as the full review surface.
</task>

<notes>
Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `tranche_brief`, `project_brief`, `project_roadmap`, `tranche_manifest`, `design`, and `open_findings` artifacts before acting.

Treat `design` as the candidate design under review, not as evidence that the design has already been approved.

If `docs/index.md` is present, read it first, then use it to select relevant specs, architecture docs, development docs, and findings docs before reviewing.

Review the candidate design from scratch before reconciling carried-forward findings.

Treat the rejection bullets as review aids, not an equal-weight checklist. Focus findings on gaps that would materially affect the tranche outcome, force later phases to invent important decisions, or create avoidable long-lived debt.

Treat generated reports, projections, summaries, and review evidence as derived outputs by default. Require them as design-level contract surfaces only when they are the maintained source of truth, a stable downstream input, or an explicit user-facing deliverable.

Reject designs that:
- conflict with the project roadmap or selected tranche brief without explaining and justifying the change
- are not self-contained enough for generic plan and implementation phases that will consume only the design and plan
- omit the selected tranche objective, relevant manifest fields, prerequisites, roadmap constraints, target artifacts, design depth, or completion gate
- omit semantically material choices or fail to justify them
- make broad claims such as full parity, full support, or release readiness without defining the behavior denominator and evidence standard
- carry forward unnecessary or counterproductive transformations, adapters, defaults, or inherited conventions
- ignore relevant roadmap layout or ownership conventions, or invent conflicting locations without explicit justification
- omit required architecture, interface, data-flow, ownership, oracle, provenance, migration, or compatibility decisions
- propose implementation before blocking design decisions are resolved
- hide work in vague "follow existing pattern" language where the existing pattern may be wrong for the tranche outcome
- make multiple surfaces authoritative for the same fact without naming one maintained source of truth and the derivation path for the others
- leave unclear what is authored versus derived, who owns it, or what must validate it when that distinction affects the tranche contract
- introduce or change a nontrivial subsystem, process, integration surface, automation, or stable consumed contract without explicit component boundaries, ownership, interfaces, invariants, failure modes, and test or review boundaries
- omit cross-tranche family analysis when the roadmap or repository evidence shows a repeated work shape
- duplicate prior tranche-local mechanics for a second or later family member without deciding whether to reuse, refactor into shared helpers, or justify a local fork
- refactor prior tranche work without preserving prior behavior, interfaces, and regression checks
- group concrete things that should change or be reviewed independently without a clear reason
- embed large hand-curated data in executable code without justifying the choice based on reviewability, provenance, and expected reuse
- provide weak verification for the tranche risk
- create avoidable debt or drift in stable project modules

Approve when the design fixes the implementation shape, ownership boundaries, cross-tranche reuse boundary where relevant, major contracts, and acceptance gates. Leave exhaustive enumerations and command-level details to the plan unless they change architecture, provenance, claims, reuse boundaries, or gate semantics.
<output instruction>
Write a JSON review report to the path recorded by the output contract's `design_review_report_path` pointer. Also write the decision token to `design_review_decision` and unresolved counts to the count files.

The report must contain:
- `decision`: `APPROVE`, `REVISE`, or `BLOCK`
- `summary`
- `findings`: array of stable findings with `id`, `severity`, `status`, `title`, `evidence`, `impact`, and `required_change`
- `unresolved_high_count`
- `unresolved_medium_count`

Use `REVISE` for fixable design problems. Use `BLOCK` only when the tranche cannot be designed from the available brief, roadmap, manifest, and repository context.
</output instruction>
</notes>
