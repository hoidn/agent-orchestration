# AGENTS.md

Read `docs/index.md` before making changes.

Repo expectations:
- Read `docs/index.md` before deciding what docs or specs govern the task.
- Use the `tmux` skill when launching long-running commands.
- Write plans under `docs/plans/` before large edits.
- Keep changes scoped to the task; avoid unrelated refactors.
- Run commands from the repo root so imports, relative paths, and fixture layout stay stable.
- Run visible checks before claiming completion.
- Treat fresh command output as required verification evidence.
- Prefer the narrowest relevant `pytest` selectors first.
- If you add or rename tests, run `pytest --collect-only` on those modules.
- Changes to workflows, prompts, artifact contracts, provisioning, or demo trial mechanics should rerun at least one orchestrator/demo smoke check in addition to unit tests.
- Do not add or keep tests that assert literal prompt text or prompt phrasing. Prefer behavioral, contract, artifact-lineage, or dataflow assertions that stay valid when prompts are revised.
- Record what you changed and how you verified it.

Do not assume success from inspection alone when runnable checks are available.
Do not weaken verification just to make a failure disappear.
Do not create worktrees, especially not when executing plans or implementing features
When a workflow run has already passed an approval/review gate and later fails downstream, prefer `orchestrator resume <run_id>` over launching a fresh run unless you intentionally want to redo the earlier gated stages.
