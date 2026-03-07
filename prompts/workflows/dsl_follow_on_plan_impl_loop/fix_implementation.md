use receiving-code-review to address the feedback

Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `design`, `plan`, `execution_report`, and `implementation_review_report` artifacts before acting.

Apply the review feedback to the repo while staying aligned with the design and plan. Use executing-plans if appropriate.
The authoritative workspace for this step is the workflow run workspace root, not any git worktree or alternate checkout.
Do not create, enter, or use `git worktree`, and do not move the work to another checkout.
If the git state in the run workspace is dirty, clean the run workspace before applying fixes instead of switching workspaces.
Any output-contract files, including the execution report and pointer files, must be written in the run workspace paths that already exist for this run.
Update the execution report at the workspace-relative path stored in `state/execution_report_path.txt` so the next review pass has current evidence.
Finally, stage and commit your changes
