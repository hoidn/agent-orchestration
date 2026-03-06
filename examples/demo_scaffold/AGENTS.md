# AGENTS.md

Read `docs/index.md` before making changes.

Repo expectations:
- Treat `state/task.md` as the canonical task description.
- Write plans under `docs/plans/` before large edits.
- Keep changes scoped to the task; avoid unrelated refactors.
- Run visible checks before claiming completion.
- Prefer the narrowest relevant `pytest` selectors first.
- If you add or rename tests, run `pytest --collect-only` on those modules.
- Run commands from the repo root so paths and imports resolve consistently.
- Record what you changed and how you verified it.

Do not assume success from inspection alone when runnable checks are available.
Do not weaken verification just to make a failure disappear.
