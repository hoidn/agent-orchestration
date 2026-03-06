# Demo Task Seed: Multiclass Metrics Port

This task-specific seed extends the generic demo scaffold with a bounded Python-to-Rust translation problem.

Design style:
- inspired by the same virtues as Karpathy-style pure Python references: small, readable, self-contained numerical code
- intentionally narrower than a full learner or training loop so the demo measures workflow hygiene, not dependency wrestling

Task shape:
- visible Python reference implementation under `src_py/`
- target Rust crate under `rust/`
- canonical task description under `docs/tasks/`

The hidden evaluator is intentionally not included in this tree.
