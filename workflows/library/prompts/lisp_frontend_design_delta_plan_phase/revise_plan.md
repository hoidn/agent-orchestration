Revise the plan to resolve review findings while preserving the selected Lisp
frontend work-item scope and target/baseline design and gap architecture
authority.

When revising, do not reintroduce manifest, conformance, parity, summary,
inventory, or status-label work as blocking implementation tasks unless that
artifact is a direct runtime input or proves the current behavior is wrong.
If the plan cannot be made executable because the consumed design or gap
architecture requires a route, mechanism, or artifact that is absent from or
contradicted by the current checkout, name that requirement explicitly in the
report as the causal finding instead of iterating.

Read the current plan at `request.subject.plan_path`, the gap architecture at
`request.subject.work_item_context.architecture_path`, and the findings JSON
at `request.subject.findings_items_path`.
Write the revised plan directly to `request.targets.plan_target_path` and
return `{"plan_path": "<that same path>"}` at the output-contract path.
