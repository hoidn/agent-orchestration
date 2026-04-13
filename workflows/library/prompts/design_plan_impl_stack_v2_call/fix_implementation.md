Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `design`, `plan`, `execution_report`, and `implementation_review_report` artifacts before acting.

Use executing-plans to address the implementation review while staying aligned with the design and the full approved plan.
Do not use `git worktree` or another checkout.
If the repo is dirty, stay in the current checkout and leave unrelated files alone.
Do not modify workflow YAML, prompt files, or runtime state files unless the plan explicitly requires it.

Your task may include either or both of:
- fixing defects or regressions in already-implemented work
- implementing the next coherent required tranche that is still unfinished

Determine remaining work by:
1. reading the consumed `plan`
2. reading the consumed `implementation_review_report`
3. inspecting the current codebase and execution report

Do not assume the review report is complete.
If the review misses required unfinished plan tasks, you should still identify and implement the next coherent required tranche yourself.

Prioritize in this order:
1. fix any blocking high-severity correctness or contract issues in already-implemented work
2. identify the earliest required unfinished plan task or coherent tranche
3. implement that tranche before optional later work

For the output contract's `execution_report_path`, read the path recorded in that file and write the concise execution report to that current-checkout-relative path. Leave the `execution_report_path` file containing only the path.

The execution report must include:
- `Completed In This Pass`
- `Completed Plan Tasks`
- `Remaining Required Plan Tasks`
- `Verification`
- `Residual Risks`

Finally, stage and commit only the implementation changes with a descriptive commit message.
