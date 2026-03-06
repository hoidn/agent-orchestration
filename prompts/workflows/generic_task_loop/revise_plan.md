Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read every consumed artifact before acting.

Also read these repo-local references:
- `docs/plans/templates/artifact_contracts.md`
- `docs/plans/templates/check_plan_schema.md`
- `docs/plans/templates/plan_template.md`

Task:
Revise the current plan and check plan to resolve the blocking findings from the plan review.

Required behavior:
- Preserve the original task scope unless the review report identifies a specific scope error.
- Update the plan so it is concrete and executable.
- Update the check plan so it is runnable and better aligned with the task.
- Resolve the cited blocking issues directly rather than rewriting everything from scratch unless that is necessary.

Required outputs:
- Produce an updated `plan` artifact.
- Produce an updated `check_plan` artifact.
- Write every required artifact exactly as specified by the output contract for this invocation.

Constraints:
- Do not implement the task in this step.
- Do not ignore cited blocking findings.
- Do not introduce hidden-evaluator assumptions into the visible check plan.
