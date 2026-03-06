Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read every consumed artifact before acting.

Also read these repo-local references:
- `docs/plans/templates/artifact_contracts.md`
- `docs/plans/templates/review_template.md`

Task:
Review the implementation for blocking correctness issues using the task, current plan, check plan, execution report, and concrete check results.

Decision rule:
- `APPROVE` only if no blocking correctness issues remain.
- `REVISE` if checks failed, if blocking correctness gaps remain, or if verification is inadequate relative to the task.

Review priorities:
- correctness
- task/plan alignment
- adequacy of visible verification
- evidence from concrete artifacts and check results

Do not reject for:
- formatting
- naming preferences
- style-only refactors
- non-blocking cleanup suggestions

Required outputs:
- Produce a review report with blocking findings, evidence, and required fixes.
- Produce the binary review decision required by the output contract.
- Write every required artifact exactly as specified by the output contract for this invocation.

Constraints:
- Base the verdict on concrete evidence.
- If checks passed but hidden-evaluator-like risks remain visible from code or artifacts, call them out and reject only if they are genuinely blocking.
