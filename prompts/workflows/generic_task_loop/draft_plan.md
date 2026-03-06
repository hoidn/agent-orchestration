Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read every consumed artifact before acting.

Also read these repo-local references before drafting outputs:
- `docs/plans/templates/artifact_contracts.md`
- `docs/plans/templates/check_plan_schema.md`
- `docs/plans/templates/plan_template.md`

Task:
- Derive an executable implementation plan from the current task.
- Derive a visible verification strategy from the task and current repo state.
- Derive and document the proposed design before listing implementation steps.

Required outputs:
- Produce a `plan` artifact that is concrete, scoped, and executable.
- Produce a `check_strategy` artifact that explains the intended visible verification and expected runnable checks.
- Write every required artifact exactly as specified by the output contract for this invocation.

Planning requirements:
- Restate the task in engineering terms.
- Define scope and non-goals.
- Call out assumptions and risks.
- Describe the proposed design, including module/function boundaries, important interfaces or data shapes, and key invariants.
- Describe the implementation sequence.
- Align the plan with a realistic visible verification strategy.

Verification-strategy requirements:
- Prefer high-signal behavioral checks over broad or noisy ones.
- Distinguish between checks that already exist and checks that should be created during execution.
- Do not fabricate runnable commands that do not exist yet.
- Do not rely on hidden evaluator behavior.

Constraints:
- Do not implement the task in this step.
- Do not fabricate repo capabilities or files that do not exist.
- Do not write outputs anywhere except the contract paths required by this invocation.
