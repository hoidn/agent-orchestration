Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `design` and `plan` artifacts before acting.

use executing-plans to implement the plan while staying aligned with the design.
The authoritative workspace for this step is the workflow run workspace root, not any git worktree or alternate checkout.
Do not create, enter, or use `git worktree`, and do not move the work to another checkout.
If the git state in the run workspace is dirty, clean the run workspace before implementing instead of switching workspaces.
Any output-contract files, including the execution report and pointer files, must be written in the run workspace paths that already exist for this run.
Write a concise execution report to the workspace-relative path stored in `state/execution_report_path.txt`.

The report should summarize what changed, what remains risky, and what verification you ran.
Finally, stage and commit with a descriptive commit message.
