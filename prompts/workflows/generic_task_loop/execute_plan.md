Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read every consumed artifact before acting.

Also read this repo-local reference:
- `docs/plans/templates/artifact_contracts.md`

Task:
Execute the current plan to complete the task within the current workspace.

Required behavior:
- Follow the plan as the primary execution guide.
- Keep work scoped to the task and current plan.
- Add or update tests and checks when the plan calls for them.
- Use engineering judgment to resolve minor implementation details that the plan leaves implicit.

Required outputs:
- Produce an `execution_report` artifact summarizing what was attempted and what changed.
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
