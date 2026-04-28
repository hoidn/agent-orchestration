Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `design` and `plan` artifacts before acting.

Use executing-plans to implement the plan in the current checkout while staying aligned with the design.
Do not use `git worktree` or another checkout.
If the repo is dirty, stay in the current checkout and leave unrelated files alone.
Do not modify workflow YAML, prompt files, or runtime state files unless the plan explicitly requires it.
Do not satisfy the plan by substituting the acceptance surface for the requested implementation. If the approved work requires behavior on a normal, public, production, default, or user-facing path, that behavior must be produced by the intended implementation path. Do not make it pass by promoting, renaming, or routing through mocks, stubs, fixtures, golden files, oracle data, cached outputs, replay tables, reference templates, candidate/dev-only helpers, fallback branches, feature flags, or test-only adapters.
Write a concise execution report to the exact path named by `state/follow-on-implementation-phase/execution_report_path.txt`.

The report should summarize what changed, what remains risky, and what verification you ran.
Finally, stage and commit with a descriptive commit message.
