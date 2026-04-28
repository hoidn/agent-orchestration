take the role of a principal engineer, expert in PLs, compilers, and agentic engineering. review the implementation derived from 2026-03-06-dsl-evolution-control-flow-and-reuse.md

Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `design`, `plan`, and `execution_report` artifacts before acting.

Review the implementation against the design and the full approved plan.

Your job is not only to find correctness bugs in the implemented tranche, but also to determine whether required approved plan tasks remain unimplemented.
Prioritize completion of unfinished required plan work over cleanup of issues in already-implemented portions, unless those issues block or materially distort subsequent required implementation or its verification.

When reviewing:
- identify required plan tasks that are still not implemented
- identify concrete implementation bugs, regressions, contract mismatches, and weak verification
- reject substitute-path closure. A result is not complete if the target behavior only passes because expected outputs, fixture data, oracle/reference artifacts, mocks, stubs, cached results, replay tables, fallback paths, dev-only helpers, feature flags, or test-only paths were moved into or made reachable from the production/default path. Review the provenance of the successful behavior, not only the final output.
- distinguish:
  - remaining required plan work
  - defects in already-implemented work that block subsequent required plan work
  - non-blocking defects in already-implemented work
  - optional later work or deliberate deferrals
If required plan tasks remain unfinished, do not let non-blocking defects in already-implemented portions dominate the review.

Write the review as markdown to the workspace-relative path stored in `state/follow-on-implementation-phase/implementation_review_report_path.txt`.
Write `APPROVE` or `REVISE` to `state/follow-on-implementation-phase/implementation_review_decision.txt`.

Group findings by severity.
If there are any high-severity findings, include a section header exactly `## High`.
If there are no high-severity findings, do not emit a `## High` section.
Include a section `## Remaining Required Plan Tasks` if any approved required plan tasks are still unimplemented.
In that section, name the next coherent required tranche that should be implemented next.
Name that tranche based on plan order, code coherence, and verification boundary.
Approve only if:
- there is no `## High` section
- no required approved plan tasks remain unimplemented
