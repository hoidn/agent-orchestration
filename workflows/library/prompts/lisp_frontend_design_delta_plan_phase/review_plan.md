Review the consumed Lisp frontend plan.

Approve only if the plan can be executed as written and follows the design and repo conventions.
Return `REVISE` for concrete high-severity scope, contract, API, fixture, or verification gaps.
Return `REVISE` if the plan changes a file used outside the selected gap's
files but only proves the selected gap works.
Return `REVISE` if a broad/default check with known unrelated existing drift is
used as a blocking implementation gate instead of being narrowed to the current
scope or recorded as follow-up drift.
Do not reject a plan solely because it omits manifest, conformance, parity,
summary, inventory, or status-label refresh. Reject only when the omission
leaves current source/runtime behavior unproven, unsafe, or inconsistent.
For medium verification gaps, approve with notes.

Write the review report to the relpath recorded in
`plan_review_report_path.txt` and write `APPROVE` or `REVISE` to
`plan_review_decision.txt`.
