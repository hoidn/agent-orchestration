Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `design` and `plan` artifacts before acting.

Use executing-plans to implement the approved plan in the current checkout.
Do not use `git worktree` or another checkout.
If the repo is dirty, stay in the current checkout and leave unrelated files alone.
Do not modify workflow YAML, prompt files, or runtime state files unless the plan explicitly requires it.

For the output contract's `execution_report_path`, read the path recorded in that file and write the concise execution report to that current-checkout-relative path. Leave the `execution_report_path` file containing only the path.

The execution report must include:
- `Completed In This Pass`
- `Completed Plan Tasks`
- `Remaining Required Plan Tasks`
- `Verification`
- `Residual Risks`

Finally, stage and commit only the implementation changes with a descriptive commit message.
