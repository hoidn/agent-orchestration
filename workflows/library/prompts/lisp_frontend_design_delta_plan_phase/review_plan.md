Review the Lisp frontend plan at `request.subject.plan_path` using the typed
request's target design, baseline design, and work-item context. Read the gap
architecture at `request.subject.work_item_context.architecture_path`.

Approve only if the plan can be executed as written and follows the design and repo conventions.
Return `REVISE` for concrete high-severity scope, contract, API, fixture, or verification gaps.
For medium verification gaps, approve with notes.
Reject plans that contradict the gap architecture.
Do not reject a plan solely because it treats manifest, conformance, parity,
summary, inventory, or status-label work as follow-up rather than blocking
tasks; reject on that axis only when such an artifact is a direct runtime input
or proves the current behavior is wrong.
If the plan cannot be made executable because the consumed design or gap
architecture requires a route, mechanism, or artifact that is absent from or
contradicted by the current checkout, name that requirement explicitly in the
report as the causal finding instead of iterating.

Write the review report directly to
`request.targets.plan_review_report_target_path`. Write a findings JSON object
with a top-level `items` array under `artifacts/work`; use an empty array when
there are no findings.
Return the `ReviewDecision` bundle at the output-contract path with `variant`
`APPROVE` or `REVISE`, `review_report` referencing that report, and
`findings: {"schema_version": "ReviewFindings.v1", "items_path": "<findings path>"}`.
If review cannot proceed because of a concrete blocker, return `BLOCKED` with
the same report/findings fields and the output contract's `blocker_class`.
