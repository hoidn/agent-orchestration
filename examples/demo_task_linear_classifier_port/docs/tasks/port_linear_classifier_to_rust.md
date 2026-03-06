# Task: Port a Multiclass Linear Classifier from Python to Rust

Translate the visible Python reference module at `src_py/linear_classifier.py` into the Rust crate under `rust/`.

## Goal

Produce a Rust library that matches the Python behavior for multiclass linear-model inference and evaluation helpers.

The target is a small multiclass linear classifier, not a hidden-layer network.

This task is intentionally in the spirit of small pure-Python ML reference code: the semantics should be clear from the visible module, and the difficulty should come from preserving behavior exactly rather than integrating large frameworks.

## Required API Surface

Implement Rust equivalents for the behaviors documented in the Python module:
- validated model construction from weights and bias vectors
- logits and stable softmax probabilities for one row or a batch
- predicted labels and top-k label sets with deterministic tie-breaking
- cross-entropy loss over batches
- confusion matrix, per-class precision/recall/F1/support, and macro F1
- expected calibration error using predicted-class confidence

## Boundaries

- Use the Rust standard library only.
- Use the visible Python module as the semantic reference.
- Keep the implementation in `rust/`; do not add FFI.
- Do not add external Python dependencies.
- Do not add network, file-format, or CLI work.
- Do not add a training loop or optimizer.

In other words: do not add external Python dependencies, and do not add FFI layers.

## Semantics That Matter

- shape validation: reject empty weights, ragged weights, mismatched bias width, mismatched feature rows, empty batches, invalid targets, invalid `k`, and invalid bin counts
- stable softmax: subtract the row max before exponentiation
- deterministic tie-breaking: when logits or probabilities tie, the lower class index wins
- cross-entropy: use predicted probability for the true class after validation, and reject zero-probability true-class cases
- calibration bins: the first bin includes 0.0, the final bin includes 1.0, and empty bins contribute nothing
- macro F1 is the arithmetic mean of per-class F1 values

## Visible Verification Expectations

Derive local checks from the Rust crate. A tractable visible check entrypoint is expected to include `cargo test --manifest-path rust/Cargo.toml`.

## Non-Goals

- performance tuning beyond straightforward, correct Rust
- Python bindings or embedding
- GPU, tensor, or array-library integration
- hidden-layer networks or backpropagation
