Review the consumed Lisp frontend plan.

Approve only if the plan can be executed as written and follows the design and repo conventions.
Return `REVISE` for any concrete medium-or-higher scope, contract, API, fixture, or verification gap.
Do not reject a plan solely because it omits manifest, conformance, parity,
summary, inventory, or status-label refresh. Reject only when the omission
leaves current source/runtime behavior unproven, unsafe, or inconsistent.

Write the review report to the relpath recorded in
`plan_review_report_path.txt` and write `APPROVE` or `REVISE` to
`plan_review_decision.txt`.
