# Task: Port a Sliding-Window Utility from Python to Rust

Translate the visible Python reference module at `src_py/sliding_window.py` into the Rust crate under `rust/`.

## Goal

Produce a Rust library that matches the Python behavior for deterministic sliding-window extraction over 1-D numeric sequences.

The target is a small ML-adjacent data utility, not a full preprocessing framework.

This task is intentionally in the spirit of small pure-Python data-pipeline helpers: the semantics should be clear from the visible module, and the difficulty should come from preserving behavior exactly rather than integrating large frameworks.

## Required API Surface

Implement Rust equivalents for the behaviors documented in the Python module:
- validated sliding-window extraction over a numeric sequence
- explicit window start-index calculation
- stride handling
- optional `drop_last` / drop-last behavior for incomplete tails
- optional tail padding when `pad_value` is provided

## Boundaries

- Use the Rust standard library only.
- Use the visible Python module as the semantic reference.
- Keep the implementation in `rust/`; do not add FFI.
- Do not add external Python dependencies.
- Do not add network, file-format, or CLI work.
- Do not add multidimensional array libraries or framework-specific preprocessing code.

In other words: do not add external Python dependencies, and do not add FFI layers.

## Semantics That Matter

- validation: reject empty inputs, non-positive `window_size`, non-positive `stride`, and contradictory tail modes
- deterministic starts: window starts advance by exactly `stride`
- tail handling:
  - if `drop_last` is `true`, discard incomplete trailing windows
  - if `drop_last` is `false` and `pad_value` is provided, pad the final window to full length
  - if `drop_last` is `false` and `pad_value` is absent, include the shorter trailing window as-is
- windows are returned in encounter order
- start indices reflect the windows actually produced

## Visible Verification Expectations

Derive local checks from the Rust crate. A tractable visible check entrypoint is expected to include `cargo test --manifest-path rust/Cargo.toml`.

## Non-Goals

- performance tuning beyond straightforward, correct Rust
- Python bindings or embedding
- GPU, tensor, or array-library integration
- 2-D image patch extraction or framework-specific dataset loaders
