# Port the nanoBragg accumulation subsystem to PyTorch

Use `state/task.md` as the canonical task description during a real run. This file is the canonical task fixture for the seed.

## Objective

Port the scoped detector pixel intensity accumulation subsystem from `src_c/nanoBragg.c` into a clean PyTorch module under `torch_port/`.

This is not a straight C-to-Python transliteration task. The target implementation is expected to restructure the loop-heavy C logic into tensor-oriented PyTorch code.

## Required source boundary

Work only within the bounded subsystem documented in `src_c/README.md`, centered on the detector pixel loops and the accumulation path that combines:
- detector subpixel coordinate construction
- solid-angle and detector-thickness capture terms
- source-vector and scattering-vector setup
- polarization and lattice-related multiplicative factors
- final accumulation into the detector image tensor

## Requirements

- restructure the legacy logic into small PyTorch helpers instead of transliterating the whole C file
- convert major per-pixel, per-subpixel, and geometry computations from scalar loop-carried state into batched tensor operations wherever the fixture scope allows
- do not treat a literal nested-loop port with PyTorch scalar math as a satisfactory end state unless a specific loop cannot be removed without changing scoped behavior
- make the tensorization strategy explicit in the implementation: identify which dimensions are batched in tensors and which dimensions, if any, remain iterative
- preserve tensor-level numerical parity for the scoped input corpus
- keep the implementation in `torch_port/`
- treat visible smoke checks as incomplete local evidence, not as full proof of correctness
- derive and run the strongest local `pytest` checks you can from the repo state
- treat parity-relevant values in the visible fixtures as authoritative inputs; do not invent hidden defaults for values such as `crystal.default_F`

## Visible input contract

The visible fixture JSON is the semantic input contract for this scoped task.

If a value materially affects numerical parity for the scoped subsystem, it should appear explicitly in the visible fixture or be explicitly ruled out by the task. Do not guess missing parity-relevant values from convention when the visible fixture contract already carries them.

In particular:
- `crystal.default_F` is an explicit visible input for this task seed
- if the fixture provides `crystal.default_F`, use that value rather than inventing a fallback
- if a parity-relevant value is genuinely absent from the fixture contract, treat that as a seed/task contract problem to document rather than silently guessing

## Restructuring expectation

The goal is to move from legacy imperative loop structure toward a PyTorch-native formulation.

Concretely:
- detector geometry, pixel coordinates, subpixel coordinates, and other per-sample quantities should be represented as tensors rather than recomputed as independent Python scalars in deeply nested loops
- broadcasting, tensor reshaping, and batched arithmetic should be preferred over scalar accumulation loops when they preserve the scoped numerical behavior
- small residual loops are acceptable only when they are justified by the scoped model structure, such as over a compact set of phi values or mosaic domains, and even then the plan should treat them as deliberate exceptions

The implementation will be judged in part on whether it actually performs this loop-to-tensor restructuring, not just on whether it produces finite outputs.

## Visible verification

- visible verification command: `pytest -q`
- visible smoke checks are incomplete by design
- the trial environment is assumed to already provide `torch`

## Out of scope

- do not port the entire program
- no CLI parsing or command-line compatibility work
- no file I/O or output serialization
- no CUDA or GPU support
- no performance targets or benchmarking gates
- no external services
