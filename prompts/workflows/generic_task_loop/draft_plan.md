Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read every consumed artifact before acting.

Also read these repo-local references before drafting outputs:
- `docs/plans/templates/artifact_contracts.md`
- `docs/plans/templates/check_plan_schema.md`
- `docs/plans/templates/plan_template.md`

Task:
- Derive an executable implementation plan from the current task.
- Derive a runnable visible verification plan from the task and current repo state.

Required outputs:
- Produce a `plan` artifact that is concrete, scoped, and executable.
- Produce a `check_plan` artifact that follows the check-plan schema and contains runnable checks.
- Write every required artifact exactly as specified by the output contract for this invocation.

Planning requirements:
- Restate the task in engineering terms.
- Define scope and non-goals.
- Call out assumptions and risks.
- Describe the implementation sequence.
- Align the plan with a realistic visible verification strategy.

Check-plan requirements:
- Use structured `argv` commands, not shell strings, unless the surrounding contract explicitly allows otherwise.
- Include only checks that are runnable in the current repo.
- Prefer high-signal checks over broad or noisy ones.
- Do not rely on hidden evaluator behavior.

Constraints:
- Do not implement the task in this step.
- Do not fabricate repo capabilities or files that do not exist.
- Do not write outputs anywhere except the contract paths required by this invocation.
