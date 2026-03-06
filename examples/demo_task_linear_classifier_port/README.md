# Demo Task Seed: Linear Classifier Port

This task-specific seed extends the generic demo scaffold with a bounded Python-to-Rust translation problem.

Design style:
- inspired by the same virtues as small pure Python ML references: readable, self-contained numerical code
- intentionally centered on inference and evaluation rather than training loops or framework integration
- harder than a metrics-only port, but still small enough for a single workflow run

Task shape:
- visible Python reference implementation under `src_py/`
- target Rust crate under `rust/`
- canonical task description under `docs/tasks/`

The hidden evaluator is intentionally not included in this tree.
