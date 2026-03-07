take the role of a principal engineer, expert in PLs, compilers, and agentic engineering. review the implementation derived from 2026-03-06-dsl-evolution-control-flow-and-reuse.md

Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `design`, `plan`, and `execution_report` artifacts before acting.

Review the implementation against the design and the full approved plan.

Your job is not only to find correctness bugs in the implemented tranche, but also to determine whether required approved plan tasks remain unimplemented.

When reviewing:
- identify concrete implementation bugs, regressions, contract mismatches, and weak verification
- identify required plan tasks that are still not implemented
- distinguish:
  - defects in already-implemented work
  - remaining required plan work
  - optional later work or deliberate deferrals

Write the review as markdown to the workspace-relative path stored in `state/implementation_review_report_path.txt`.
Write `APPROVE` or `REVISE` to `state/implementation_review_decision.txt`.

Group findings by severity.
If there are any high-severity findings, include a section header exactly `## High`.
If there are no high-severity findings, do not emit a `## High` section.
Include a section `## Remaining Required Plan Tasks` if any approved required tasks are still unimplemented.
In that section, name the next coherent required tranche that should be implemented next.
Name that tranche based on plan order, code coherence, and verification boundary.
Approve only if:
- there is no `## High` section
- no required approved plan tasks remain unimplemented
