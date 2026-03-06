Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read every consumed artifact before acting.

Also read this repo-local reference:
- `docs/plans/templates/artifact_contracts.md`

Task:
Fix the blocking issues identified in the latest implementation review while staying within the task scope and current plan.

Required behavior:
- Prioritize concrete failing checks and cited blocking findings.
- Keep changes tightly scoped to the required fixes.
- Update tests or checks when needed to support the fix.
- Refresh the execution report to reflect the latest work.

Required outputs:
- Produce an updated `execution_report` artifact.
- Write every required artifact exactly as specified by the output contract for this invocation.

The updated execution report should include:
- fixes implemented
- files changed
- commands executed
- tests or checks added or modified
- remaining blockers or unresolved risks

Constraints:
- No unrelated refactors.
- No fabricated results.
- Do not silently ignore cited blocking findings.
