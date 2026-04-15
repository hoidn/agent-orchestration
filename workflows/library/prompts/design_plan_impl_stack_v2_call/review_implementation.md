take the role of a principal engineer, expert in PLs, compilers, and agentic engineering. review the implementation against the approved design and plan

Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `design`, `plan`, and `execution_report` artifacts before acting.

Review the implementation against the design and the full approved plan.

Your job is not only to find correctness bugs in the implemented tranche, but also to determine whether required approved plan tasks remain unimplemented.
Prioritize completion of unfinished required plan work over cleanup of issues in already-implemented portions, unless those issues block or materially distort subsequent required implementation or its verification.

When reviewing:
- identify required plan tasks that are still not implemented
- identify concrete implementation bugs, regressions, contract mismatches, and weak verification
- flag implementation files that are large or complex because they combine hand-curated data, generation logic, validation, and report rendering; require either a justified one-off rationale or a split into clearer source data, generator, validator, and output/report files
- use systematic-debugging to identify the root cause of any nontrivial runtime failures
- distinguish:
  - remaining required plan work
  - defects in already-implemented work that block subsequent required plan work
  - non-blocking defects in already-implemented work
  - optional later work or deliberate deferrals

For the output contract's `implementation_review_report_path`, read the path recorded in that file and write the review markdown to that current-checkout-relative path. Leave the `implementation_review_report_path` file containing only the path.
Write `APPROVE` or `REVISE` to the `implementation_review_decision` path specified in the Output Contract.

Group findings by severity.
If there are any high-severity findings, include a section header exactly `## High`.
If there are no high-severity findings, do not emit a `## High` section.
Include a section `## Remaining Required Plan Tasks` if any approved required plan tasks are still unimplemented.
In that section, name the next coherent required tranche that should be implemented next.
Name that tranche based on plan order, code coherence, and verification boundary.
Approve only if:
- there is no `## High` section
- no required approved plan tasks remain unimplemented
