use receiving-code-review to address the feedback

Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `design`, `plan`, `execution_report`, and `implementation_review_report` artifacts before acting.

Apply the review feedback to the repo while staying aligned with the design and full approved plan. Use executing-plans if appropriate.
Do not use `git worktree` or another checkout.
If the repo is dirty, stay in the current checkout and leave unrelated files alone.
Do not modify workflow YAML, prompt files, or runtime state files unless the plan explicitly requires it.

Your task may include either or both of:
- fixing defects or regressions in already-implemented work
- implementing the next required plan tranche that is still unfinished

Determine remaining work by:
1. reading the consumed `plan`
2. reading the consumed `implementation_review_report`
3. inspecting the current codebase and execution report

Do not assume the review report is complete.
If the review misses required unfinished plan tasks, you should still identify and implement the next coherent required tranche yourself.
Choose that tranche based on plan order, code coherence, and verification boundary.

Prioritize in this order:
1. fix any high-severity correctness or contract issues in already-implemented work
2. identify the earliest required unfinished plan task or tranche
3. implement the next coherent required tranche before optional later work

Do not satisfy the review by substituting the acceptance surface for the requested implementation. If the approved work requires behavior on a normal, public, production, default, or user-facing path, that behavior must be produced by the intended implementation path. Do not make it pass by promoting, renaming, or routing through mocks, stubs, fixtures, golden files, oracle data, cached outputs, replay tables, reference templates, candidate/dev-only helpers, fallback branches, feature flags, or test-only adapters. If the only working path is one of those evidence/helper paths, preserve the blocker and record the missing production implementation.

Update the execution report at the exact path named by `state/follow-on-implementation-phase/execution_report_path.txt` so the next review pass has current evidence.
The execution report must include these sections:
- `Completed In This Pass`
- `Completed Plan Tasks`
- `Remaining Required Plan Tasks`
- `Verification`
- `Residual Risks`

Finally, stage and commit your changes
