# Port the nanoBragg accumulation subsystem to PyTorch

Use `state/task.md` as the canonical task description during a real run. This file is the canonical task fixture for the seed.

## Objective

Port the scoped detector pixel intensity accumulation subsystem from `src_c/nanoBragg.c` into a clean PyTorch module under `torch_port/`.

## Required source boundary

Work only within the bounded subsystem documented in `src_c/README.md`, centered on the detector pixel loops and the accumulation path that combines:
- detector subpixel coordinate construction
- solid-angle and detector-thickness capture terms
- source-vector and scattering-vector setup
- polarization and lattice-related multiplicative factors
- final accumulation into the detector image tensor

## Requirements

- restructure the legacy logic into small PyTorch helpers instead of transliterating the whole C file
- preserve tensor-level numerical parity for the scoped input corpus
- keep the implementation in `torch_port/`
- treat visible smoke checks as incomplete local evidence, not as full proof of correctness
- derive and run the strongest local `pytest` checks you can from the repo state

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
