use receiving-code-review to address the feedback

Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `design`, `plan`, `execution_report`, and `implementation_review_report` artifacts before acting.

Apply the review feedback to the repo while staying aligned with the design and plan. Use executing-plans if appropriate.
Do not use `git worktree` or another checkout.
If the repo is dirty, stay in the current checkout and leave unrelated files alone.
Do not modify workflow YAML, prompt files, or runtime state files unless the plan explicitly requires it.
Update the execution report at the exact path named by `state/execution_report_path.txt` so the next review pass has current evidence.
Finally, stage and commit your changes
