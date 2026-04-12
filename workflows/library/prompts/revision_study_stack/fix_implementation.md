Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `approved_design`, `revision_context`, `plan`, `execution_report`, and `implementation_review_report` artifacts before acting.

Fix the implementation according to the review while staying aligned with the approved design and full plan.
Do not use `git worktree` or another checkout.
If the repo is dirty, leave unrelated files alone.
Do not edit the original revision design seed unless the approved plan explicitly requires it.
Do not commit unless the approved plan explicitly requires a commit.

Your task may include either or both of:
- fixing defects or provenance gaps in already-completed work
- implementing the next coherent required tranche that remains unfinished

Do not assume the review report is complete. Re-read the approved plan and current checkout before deciding what remains.

Write an updated execution report to the path recorded by the `execution_report_path` output-contract pointer.

The execution report must include:
- `Completed In This Pass`
- `Completed Plan Tasks`
- `Generated Or Updated Artifacts`
- `Verification`
- `Pivots Or Stop Conditions`
- `Remaining Required Plan Tasks`
- `Residual Risks`
