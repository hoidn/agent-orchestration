take the role of a principal engineer, expert in PLs, compilers, and agentic engineering. review the implementation against the approved design and plan

Major-project implementation escalation additions:
- Read the consumed `implementation_iteration_context` artifact.
- Allowed decisions are `APPROVE`, `REVISE`, `ESCALATE_REPLAN`, and `BLOCK`.
- If a remaining high-severity blocker is not directly actionable under the approved plan, use `ESCALATE_REPLAN` regardless of `threshold_crossed`.
- If `threshold_crossed` is true, explicitly assess whether local implementation is still the right locus.
- Use `ESCALATE_REPLAN` when the plan/task decomposition or sequencing is the problem, including when the evidence suggests the plan phase may need to escalate to redesign.
- Use `BLOCK` when the implementation cannot be reviewed safely from the available artifacts.
- Write an implementation escalation context JSON to the target named by the `implementation_escalation_context_path` output. It may be inactive for `APPROVE` or `REVISE`, but it must exist.

Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `design`, `plan`, and `execution_report` artifacts before acting.

Review the implementation against the design, the approved plan, the plan's stated current implementation scope, and any explicit deferrals.
Do not treat generated reports, projections, summaries, or other derived evidence artifacts as blocking by themselves unless they are the authoritative source of truth, a stable downstream input, or an explicit user-facing deliverable in the approved design or plan.

Your job is to decide whether the delivered implementation is correct, maintainable, and honestly scoped.
Unfinished work blocks approval when it was claimed complete, belongs to the approved current scope, is required for the delivered behavior to be correct, is an immediate prerequisite for the delivered behavior, or was deferred without clear authority and handoff criteria.
Weight implementation correctness, API behavior, and maintainability at least as heavily as scope-completion issues when assigning severity.

When reviewing:
- identify claimed or current-scope plan tasks that are still not implemented
- identify material design or plan requirements that were deferred without clear authority, rationale, and handoff criteria
- identify concrete implementation bugs, regressions, and contract mismatches
- flag implementations that drift from roadmap, design, or plan layout and ownership decisions, or combine things the design or plan kept separate without a recorded rationale
- use systematic-debugging to identify the root cause of any nontrivial runtime failures
- flag implementations that make tests or reports pass by expecting blocked, failing, unsupported, or candidate-only behavior when the approved target behavior is still required. Treat those changes as blocker-honesty evidence only, not as completion of the target behavior.
- for numerical parity failures in current-scope or claimed behavior, distinguish implementation defects, insufficient diagnosis, and cases where the comparison standard is too strict for the supported claim. Treat tolerance or comparator changes as acceptable only when residual evidence supports numerical-method drift rather than semantic or physics drift, unaffected invariants stay strict, and the authoritative spec, catalog, test helper, or gate is updated.
- for parity or benchmark work, reject implementations where validation data is part of the production mechanism being validated, unless the approved design explicitly defines the feature as reference-data lookup. Validation data includes expected outputs, oracle data, fixtures, generated evidence, checked-in answer tables, derived reference templates, or equivalent encoded answers. It may support tests, diagnostics, and review evidence; it must not be what makes production behavior pass.
- distinguish:
  - unfinished current-scope work
  - defects in already-implemented work that block delivered behavior
  - non-blocking defects in already-implemented work
  - follow-up work or deliberate deferrals
- classify each blocking issue as an implementation defect, missing evidence for a claim, invalid or non-runnable gate, environment blocker, or pre-existing drift. Do not treat invalid gates or unavailable environment tools as implementation defects unless the plan assigns implementation to fix them.

For the output contract's `implementation_review_report_path`, read the path recorded in that file and write the review markdown to that current-checkout-relative path. Leave the `implementation_review_report_path` file containing only the path.
Write `APPROVE`, `REVISE`, `ESCALATE_REPLAN`, or `BLOCK` to the `implementation_review_decision` path specified in the Output Contract.

Use `REVISE` only when the remaining blocking work is directly actionable under the approved plan.
Use `ESCALATE_REPLAN` when a high-severity current-scope blocker appears to require unplanned architecture, missing prerequisite machinery, a different implementation sequence, or a different task decomposition.
If the implementation review says "must implement X" but the available evidence shows that X is not executable from the approved plan, do not keep the locus at local implementation only because `threshold_crossed` is false.
If an implementation improves blocked-state honesty while the approved target behavior remains unsolved, do not approve it and do not count that honesty work as target-behavior completion.

Group findings by severity.
If there are any high-severity findings, include a section header exactly `## High`.
If there are no high-severity findings, do not emit a `## High` section.
Include a section `## Follow-Up Work` for unfinished plan work that is real but not required for approving the delivered scope.
If `threshold_crossed` is true and the decision remains `REVISE`, include a section `## Escalation Assessment` explaining why continued local implementation is still justified.
Approve only if:
- there is no `## High` section
- no claimed or current-scope plan tasks remain unimplemented
- no unfinished prerequisite makes the delivered behavior unsafe, misleading, or unusable
- no material design requirement was silently dropped or deferred without authority
