# AGENTS.md

Read `docs/index.md` before making changes.

Repo expectations:
- Treat `state/task.md` as the canonical injected task description during a run.
- The task-specific source material lives in `src_py/multiclass_metrics.py` and `docs/tasks/`.
- Keep changes scoped to the task; avoid unrelated refactors.
- Run visible checks before claiming completion.
- Record what you changed and how you verified it.

Do not add FFI layers, Python bindings, or external Python dependencies unless the task explicitly requires them.
