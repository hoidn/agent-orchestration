# Demo Scaffold Seed

This directory is the visible seed tree for the direct-vs-workflow demo.

It is intentionally small and task-neutral. A task-specific demo should copy this tree into a seed repository, then add:
- the visible task description at `state/task.md`
- any visible reference code under `src_py/`
- any target project skeleton under `rust/`
- any visible smoke checks that both arms are allowed to use

The hidden evaluator must remain outside this tree.
