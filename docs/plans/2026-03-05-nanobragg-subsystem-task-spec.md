# nanoBragg Subsystem Task Spec

> Superseded as the flagship benchmark by `docs/plans/2026-03-06-harder-nanobragg-entrypoint-design.md`.
> Keep this document as historical context for the older narrowed accumulation task only.

## Goal

Define a significantly harder flagship demo task than the current linear-classifier port by scoping a single numerically meaningful subsystem from `nanoBragg.c` and requiring a PyTorch port with restructuring plus tensor-level numerical parity.

This task is intended for the direct-vs-workflow demo. It should be hard enough that a direct single-shot agent often produces a plausible but incomplete result, while the workflow has a realistic path to succeed via plan, review, checks, and fix loops.


## Current Flagship Contract

The current flagship demo task is narrower than the original aspirational subsystem described below.

For demo fairness, the authoritative acceptance target is now the scoped contract in:
- `examples/demo_task_nanobragg_accumulation_port/docs/tasks/nanobragg_accumulation_contract.md`

That narrowed contract is derived from the offline reference harness and is the source of truth for:
- user-facing task wording
- visible seed guidance
- workflow review expectations
- hidden evaluator behavior

Broader expansion toward a richer nanoBragg-like subsystem remains future work, not current acceptance criteria.

## Source Location

Local copies found during this session:
- `../nanoBragg/golden_suite_generator/nanoBragg.c`
- `../tmp/nanoBragg/golden_suite_generator/nanoBragg.c`
- `../diffbragg_example_2/diffbragg_example/nanoBragg2/nanoBragg.c`

Recommended source of truth for initial task design:
- `../nanoBragg/golden_suite_generator/nanoBragg.c`

Reason:
- it is present locally
- it includes trace instrumentation comments and debugging support
- it appears to be a working golden-suite-oriented source tree rather than an arbitrary fork

## Recommended Subsystem

### Detector Pixel Intensity Accumulation Kernel

Scope the task to the detector sweep and intensity accumulation slice centered on the nested loops beginning around:
- `for(spixel=0;spixel<spixels;++spixel)` at approximately line 2839
- `for(fpixel=0;fpixel<fpixels;++fpixel)` at approximately line 2887

And specifically include the numerically meaningful accumulation path around the current narrowed contract:
- detector subpixel coordinate construction
- diffracted ray / airpath computation
- pixel solid angle computation (`omega_pixel`)
- detector thickness capture fraction (`capture_fraction`)
- source-weight contribution
- phi-count iteration
- mosaic-weight contribution
- final accumulation into `floatimage[imgidx]`

Out-of-contract richer physics terms such as scattering-vector behavior, polarization, and lattice-related factors are future work unless and until the reference harness is broadened with them.

Key accumulation points appear around:
- `omega_pixel` and `capture_fraction` setup near lines 2916-2981
- source / scattering / polarization setup near lines 2983-3040
- lattice and structure-factor path near lines 3200-3366
- final accumulated pixel value near lines 3380-3404

## Why This Slice

This subsystem is a good demo target because it is:
- numerically central rather than cosmetic
- structurally difficult to port line-by-line into PyTorch without redesign
- cross-cutting across geometry, detector effects, and accumulation logic
- parity-checkable on fixed inputs
- large enough to require planning and review, but still much smaller than porting all of `nanoBragg.c`

It also creates a likely direct-arm failure mode:
- incorrect indexing or broadcasting
- missing detector-thickness or solid-angle behavior
- wrong ordering of multiplicative factors
- subtle convention mismatch around per-pixel accumulation

## Task Statement

### Candidate user-facing task

Port the detector pixel intensity accumulation subsystem from `nanoBragg.c` into PyTorch.

Requirements:
- preserve tensor-level numerical behavior for the defined input corpus
- restructure the legacy loop-heavy C implementation into a clean PyTorch module
- keep the PyTorch implementation limited to the scoped subsystem
- do not attempt to port the entire program

The agent should be required to:
- identify the subsystem boundary from provided scaffolding and task text
- design a clean PyTorch API
- implement the port
- derive and run visible local checks

## Expected Restructuring

The task should explicitly require restructuring, not transliteration.

Target design expectations:
- split geometry preparation from accumulation
- represent per-pixel and per-subpixel quantities as tensors
- separate pure helper functions from orchestration
- avoid one giant monolithic PyTorch function if a small module with helpers is clearer

The task should not require:
- GPU support
- performance benchmarking as a pass condition
- full CLI parity
- porting unrelated file I/O or option parsing

## Input / Output Boundary

The subsystem task should expose a bounded pure-ish interface.

### Inputs

Prepare a fixed structured input bundle that contains only the data needed by the selected accumulation slice, for example:
- detector geometry tensors / vectors
- pixel grid dimensions
- oversample settings
- source vectors and wavelengths
- phi angles
- mosaic matrices
- detector thickness parameters
- precomputed reciprocal-space or unit-cell data needed by the scoped slice
- interpolation mode / booleans

### Outputs

At minimum:
- accumulated detector image tensor equivalent to the relevant `floatimage` slice

Optional secondary outputs if useful for debugging and parity:
- `omega_pixel` tensor
- `capture_fraction` tensor
- selected trace taps for one or more probe pixels

## Verification Strategy

### Canonical verdict

Use deterministic hidden tensor-level parity tests.

The hidden evaluator should compare:
- output tensor shape
- dtype policy if specified
- numerical parity against a fixed corpus of inputs

Recommended parity policy:
- primary: `torch.testing.assert_close`
- specify both `rtol` and `atol`
- use tighter tolerances where feasible and only relax where numerically justified

### Visible checks

Visible checks should be necessary but insufficient.

Recommended visible checks:
- a small smoke parity suite over 1-3 fixed cases
- one or two targeted trace-point checks
- basic shape and finite-value checks

The visible suite should not fully cover:
- all edge conditions
- all parameter combinations
- all convention-sensitive cases

### Hidden checks

Hidden checks should add:
- multiple geometry configurations
- varied oversampling settings
- detector-thickness on/off cases
- multiple source / phi / mosaic combinations
- convention-sensitive edge cases
- one or more cases where naive vectorization often goes wrong

## Difficulty Targets

This task should be engineered so that:
- one-pass direct success is possible but uncommon
- visible checks can pass while hidden parity still fails
- at least one workflow review/fix cycle is likely

Direct-arm failure modes the task should encourage:
- missing one multiplicative factor
- slightly wrong tensor shape or broadcasting semantics
- incorrect ordering of reductions
- incomplete handling of oversample / thickness / polarization branches

Workflow advantages the task should exercise:
- planning the subsystem boundary before coding
- explicit verification strategy design
- implementation review against concrete parity evidence
- focused repair after structured failure

## Out of Scope

To keep the task bounded, explicitly exclude:
- full `nanoBragg.c` port
- CLI parsing
- file-format readers and writers
- noise generation
- output image serialization
- all unrelated helper routines unless directly required by the selected accumulation slice
- performance thresholds

## Scaffold Recommendations

The seed repo for this task should include:
- the selected C source slice or the full file with the scoped region clearly referenced
- a PyTorch module skeleton
- a small visible parity harness
- fixed seeded fixture inputs
- task text explaining the subsystem boundary
- hidden evaluator outside the visible workspace

Helpful visible files:
- `docs/index.md`
- `AGENTS.md`
- `docs/dev_guidelines.md`
- `docs/tasks/port_nanobragg_accumulation_subsystem_to_pytorch.md`
- `src_c/nanoBragg.c` or a minimized extracted reference file
- `src_py/` or `torch_port/` target module skeleton
- `tests/` with smoke parity tests

## Recommended Next Implementation Step

Before building the seed, do one more narrowing pass:
- identify the minimal exact code region to include
- define the structured input bundle shape
- define 3-5 hidden parity fixture families
- decide whether helper functions such as `polarization_factor` are included as part of the subsystem or treated as provided dependencies

## Bottom Line

The current flagship task is:

Port the narrowed, harness-backed nanoBragg accumulation contract into PyTorch, with required restructuring and deterministic tensor-level parity against a fixed corpus of cases.

This keeps the demo fair by making task text, visible guidance, workflow review, and hidden evaluation point at the same acceptance target. Broader nanoBragg-like expansion is future work.
