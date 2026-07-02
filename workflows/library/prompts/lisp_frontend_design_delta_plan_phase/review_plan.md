Review the consumed Lisp frontend plan.

Approve only if the plan can be executed as written and follows the design and repo conventions.
Return `REVISE` for concrete high-severity scope, contract, API, fixture, or verification gaps.
For medium verification gaps, approve with notes.
Reject plans that contradict the gap architecture.
Put source or runtime behavior repair before evidence refresh. Do not plan
manifest, conformance, parity, summary, inventory, or status-label work as a
blocking implementation task unless that artifact is a direct runtime input or
proves the current behavior is wrong.
If the plan cannot be made executable because the consumed design or gap
architecture requires a route, mechanism, or artifact that is absent from or
contradicted by the current checkout, name that requirement explicitly in the
report as the causal finding instead of iterating.

Write the review report to the relpath recorded in
`plan_review_report_path.txt` and write `APPROVE` or `REVISE` to
`plan_review_decision.txt`.
