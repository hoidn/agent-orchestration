take the role of a principal engineer, expert in PLs, compilers, and agentic engineering. review the implementation derived from 2026-03-06-dsl-evolution-control-flow-and-reuse.md

Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `design`, `plan`, and `execution_report` artifacts before acting.

Review the implementation against the design and approved plan for correctness, alignment, and verification quality.
Write the review as markdown to the workspace-relative path stored in `state/implementation_review_report_path.txt`.
Write `APPROVE` or `REVISE` to `state/implementation_review_decision.txt`.

Group findings by severity.
If there are any high-severity findings, include a section header exactly `## High`.
If there are no high-severity findings, do not emit a `## High` section.
Approve only if there is no `## High` section.
