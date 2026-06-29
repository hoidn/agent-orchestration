Review the consumed Lisp frontend plan.

Approve only if the plan can be executed as written and follows the design and repo conventions.
Return `REVISE` for concrete high-severity scope, contract, API, fixture, or verification gaps.
Return `REVISE` if the plan changes code used by other tasks but only proves
the selected case works.
For medium verification gaps, approve with notes.

Write the review report to the relpath recorded in
`plan_review_report_path.txt` and write `APPROVE` or `REVISE` to
`plan_review_decision.txt`.
