Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read every consumed artifact before acting.

Also read these repo-local references:
- `docs/plans/templates/artifact_contracts.md`
- `docs/plans/templates/check_plan_schema.md`
- `docs/plans/templates/review_template.md`

Task:
Review the current plan and check strategy for executability and verification quality.

If the task defines a scoped contract, review against that scoped contract rather than against broader inferred domain behavior.

Decision rule:
- `APPROVE` only if the plan is concrete enough to execute and the check strategy provides a credible path to strong visible verification.
- `REVISE` if there are blocking scope, execution, or verification gaps.

Reject for:
- weak or missing design reasoning for a task that requires nontrivial decomposition
- unclear module or function boundaries, interfaces, or invariants
- underspecified implementation steps
- obvious correctness or scope gaps
- weak, circular, or implausible verification strategy
- failure to explain how runnable verification will exist by the implementation loop
- a strategy that is too narrow for the stated task

Do not reject for:
- style preferences
- naming preferences
- harmless wording differences

Required outputs:
- Produce a review report with concrete evidence and required fixes.
- Produce the binary review decision required by the output contract.
- Write every required artifact exactly as specified by the output contract for this invocation.

Constraints:
- Focus on whether the plan is safe and useful to execute next.
- Treat out-of-contract improvements as non-blocking unless the task explicitly requires them.
- Required fixes should be specific and actionable.
