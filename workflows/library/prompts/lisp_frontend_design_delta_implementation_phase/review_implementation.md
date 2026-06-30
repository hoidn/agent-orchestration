If you approve the implementation, stage and commit only the changes that belong
to this approved implementation before writing `APPROVE`, with a descriptive
multiline commit message.

Take the role of a principal engineer, expert in PLs, compilers, and agentic
engineering. Review the implementation against the approved design and plan.

Read the `Consumed Artifacts` section first and treat it as the authoritative
input list. Read the consumed target design, gap architecture, plan, and
execution_report artifacts before acting.

Review the implementation against the target design, the gap architecture, the
approved plan, the plan's stated current implementation scope, and any explicit
deferrals.

Your job is to decide whether the delivered implementation is correct,
maintainable, and honestly scoped.
Unfinished work blocks approval when it was claimed complete, belongs to the
approved current implementation scope, or is required for the delivered behavior
to be correct.
Weight implementation correctness, API behavior, and maintainability at least as
heavily as scope-completion issues when assigning severity.

When reviewing:
- identify claimed or current-scope plan tasks that are still not implemented
- identify material design or plan requirements that were deferred without clear
  authority, rationale, and handoff criteria
- identify concrete implementation bugs, regressions, and contract mismatches
- flag implementations that drift from roadmap, design, or plan layout and
  ownership decisions, or combine things the design or plan kept separate
  without a recorded rationale
- reject substitute-path closure. A result is not complete if the target
  behavior only passes because expected outputs, fixture data, oracle/reference
  artifacts, mocks, stubs, cached results, replay tables, fallback paths,
  dev-only helpers, feature flags, or test-only paths were moved into or made
  reachable from the production/default path. Review the provenance of the
  successful behavior, not only the final output.
- reject changes that only preserve a temporary workaround instead of removing
  it, confining it to an external boundary, or removing a specific blocker to
  deleting it.
- reject changes that make implementation-only data part of the user-facing or
  domain contract unless the governing design or spec explicitly requires it.

In the verification section, note whether relevant project-native lint/static
checks were run. Distinguish correctness-relevant findings from pre-existing or
cleanup-only lint noise.

Leave unrelated pre-existing changes unstaged, and record the commit hash in
the review report.

For the output contract's `implementation_review_report_path`, read the path
recorded in that file and write the review markdown to that
current-checkout-relative path. Leave the
`implementation_review_report_path` file containing only the path.
Write `APPROVE` or `REVISE` to the `implementation_review_decision` path
specified in the Output Contract.

Group findings by severity.
If there are any high-severity findings, include a section header exactly
`## High`.
If there are no high-severity findings, do not emit a `## High` section.
Include a section `## Follow-Up Work` for unfinished plan work that is real but
not required for approving the delivered scope.

Approve only if:
- there are no high- or medium-severity findings
- the delivered behavior matches the approved current implementation scope
- no concrete bug, contract mismatch, fixture shortcut, or missing required check remains
