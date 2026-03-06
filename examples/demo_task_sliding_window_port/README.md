# Demo Task Seed: Sliding Window Port

This task-specific seed extends the generic demo scaffold with a bounded Python-to-Rust translation problem.

Design style:
- inspired by small, dependency-free ML data utilities rather than framework-heavy preprocessing stacks
- intentionally centered on deterministic window extraction semantics instead of model training
- small enough for a single workflow run, but rich enough to reward explicit planning and verification

Task shape:
- visible Python reference implementation under `src_py/`
- target Rust crate under `rust/`
- canonical task description under `docs/tasks/`

The hidden evaluator is intentionally not included in this tree.
