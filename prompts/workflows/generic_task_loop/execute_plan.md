Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read every consumed artifact before acting.

Also read these repo-local references:
- `docs/plans/templates/artifact_contracts.md`
- `docs/plans/templates/check_plan_schema.md`

Task:
Execute the current plan to complete the task within the current workspace.

Required behavior:
- Follow the plan as the primary execution guide.
- Keep work scoped to the task, current plan, and check strategy.
- Add or update tests and checks when the plan calls for them.
- Materialize a runnable `check_plan` artifact that reflects the checks that can actually be executed now.
- Use engineering judgment to resolve minor implementation details that the plan leaves implicit.

Required outputs:
- Produce an `execution_report` artifact summarizing what was attempted and what changed.
- Produce an updated `check_plan` artifact that follows the runtime check-plan schema and contains runnable checks.
- Write every required artifact exactly as specified by the output contract for this invocation.

The execution report should include:
- plan used
- files changed
- commands executed
- tests or checks added or modified
- claimed completion status
- blockers or unresolved risks

Constraints:
- No unrelated refactors.
- No fabricated results.
- Do not treat the task as complete merely because code was written.
- Do not write outputs anywhere except the contract paths required by this invocation.
- Do not generate expected numerical outputs, oracle artifacts, or reference metrics from the candidate implementation.
- Any visible oracle artifact must come from a reference path or a pre-existing artifact with documented external provenance.
