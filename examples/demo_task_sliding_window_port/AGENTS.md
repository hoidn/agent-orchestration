# AGENTS.md

Read `docs/index.md` before making changes.

Repo expectations:
- Treat `state/task.md` as the canonical injected task description during a run.
- The task-specific source material lives in `src_py/sliding_window.py` and `docs/tasks/`.
- Keep changes scoped to the task; avoid unrelated refactors.
- Run visible checks before claiming completion.
- Prefer the narrowest relevant `pytest` selectors first.
- If you add or rename tests, run `pytest --collect-only` on those modules.
- Run commands from the repo root so paths and imports resolve consistently.
- Record what you changed and how you verified it.

Do not add FFI layers, Python bindings, training loops, or external Python dependencies unless the task explicitly requires them.
Do not weaken verification just to make a failure disappear.
