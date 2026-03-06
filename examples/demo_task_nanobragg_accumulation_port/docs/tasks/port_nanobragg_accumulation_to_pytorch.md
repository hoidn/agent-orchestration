# Port the nanoBragg accumulation contract to PyTorch

Use `state/task.md` as the canonical task description during a real run. This file is the canonical task fixture for this seed.

## Objective

Implement the scoped nanoBragg accumulation contract in PyTorch under `torch_port/`.

The authoritative behavior definition for this task is:
- `docs/tasks/nanobragg_accumulation_contract.md`

That contract, not a broader interpretation of `src_c/nanoBragg.c`, defines what behavior must be preserved.

## Required source boundary

Work only within the bounded source context documented in `src_c/README.md` and the scoped contract.

`src_c/nanoBragg.c` is visible source context for the legacy implementation shape, but the acceptance target is the narrower contract in `nanobragg_accumulation_contract.md`.

## Requirements

- preserve the scoped contract exactly
- restructure the loop-heavy legacy logic into small PyTorch helpers instead of transliterating the whole C file
- convert detector, subpixel, and geometry work into batched tensor operations where the scoped contract allows it
- do not treat a literal nested-loop port with PyTorch scalar math as a satisfactory end state unless a specific loop cannot be removed without changing the scoped contract
- make the tensorization strategy explicit in the implementation: identify which dimensions are batched in tensors and which dimensions, if any, remain iterative
- preserve tensor-level numerical parity for the scoped input corpus
- keep the implementation in `torch_port/`
- treat visible smoke checks as incomplete local evidence, not as full proof of correctness
- derive and run the strongest local `pytest` checks you can from the repo state
- use visible fixture values as authoritative scoped inputs; do not invent hidden defaults
- do not add out-of-contract model terms and treat them as required behavior

## Visible input contract

The visible fixture JSON is the semantic input contract for this scoped task.

If a value materially affects numerical parity for the scoped contract, it should appear explicitly in the visible fixture or be explicitly ruled out by the contract document. Do not guess missing parity-relevant values from convention when the visible fixture contract already carries them.

In particular:
- `crystal.default_F` is a visible seed input
- if the fixture provides `crystal.default_F`, use that value rather than inventing a fallback
- if a parity-relevant value is genuinely absent from the fixture contract, treat that as a seed/task contract problem to document rather than silently guessing

## Restructuring expectation

The goal is to move from legacy imperative loop structure toward a PyTorch-native formulation while preserving the scoped contract.

Concretely:
- detector geometry, pixel coordinates, and subpixel coordinates should be represented as tensors rather than recomputed as independent Python scalars in deeply nested loops
- broadcasting, tensor reshaping, and batched arithmetic should be preferred over scalar accumulation loops when they preserve the scoped contract
- small residual loops are acceptable only when they are justified by the scoped contract and clearly documented as deliberate exceptions

The implementation will be judged in part on whether it performs this loop-to-tensor restructuring while staying inside the contract scope.

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
- no richer out-of-contract model behavior beyond what the scoped contract requires
