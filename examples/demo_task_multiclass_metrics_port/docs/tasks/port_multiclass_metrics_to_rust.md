# Task: Port Multiclass Metrics Utilities from Python to Rust

Translate the visible Python reference module at `src_py/multiclass_metrics.py` into the Rust crate under `rust/`.

## Goal

Produce a Rust library that matches the Python behavior for multiclass classification metrics and calibration helpers.

This task is intentionally in the spirit of small pure-Python ML reference code: the semantics should be clear from the visible module, and the difficulty should come from preserving behavior exactly rather than integrating large frameworks.

## Required API Surface

Implement Rust equivalents for the behaviors documented in the Python module:
- top-k accuracy over multiclass probability rows
- confusion matrix derived from probability rows and integer class targets
- per-class precision, recall, F1, and support
- macro F1 aggregation
- expected calibration error using predicted-class confidence

## Boundaries

- Use the Rust standard library only.
- Use the visible Python module as the semantic reference.
- Keep the implementation in `rust/`; do not add FFI.
- Do not add external Python dependencies.
- Do not add network, file-format, or CLI work.

In other words: do not add external Python dependencies, and do not add FFI layers.

## Semantics That Matter

- deterministic tie-breaking: when probabilities tie, the lower class index wins
- validation: reject empty inputs, mismatched lengths, invalid class ids, invalid `k`, and invalid bin counts
- calibration bins: the first bin includes 0.0, the final bin includes 1.0, and empty bins contribute nothing
- macro F1 is the arithmetic mean of per-class F1 values

## Visible Verification Expectations

Derive local checks from the Rust crate. A tractable visible check entrypoint is expected to include `cargo test --manifest-path rust/Cargo.toml`.

## Non-Goals

- performance tuning beyond straightforward, correct Rust
- Python bindings or embedding
- GPU, tensor, or array-library integration
