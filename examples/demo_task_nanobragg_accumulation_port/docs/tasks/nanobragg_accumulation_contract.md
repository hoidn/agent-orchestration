# nanoBragg Accumulation Contract

This document is the authoritative scoped behavior contract for the demo task in this seed.

The task is not "port the richest plausible nanoBragg-like subsystem." The task is to preserve the behavior of the current scoped offline reference harness while restructuring detector and subpixel work into PyTorch tensor operations.

## Reference Source

The executable reference for this contract is the offline harness in:
- `scripts/demo/nanobragg_reference/reference_harness.c`
- `scripts/demo/nanobragg_reference/run_reference_case.py`

The visible task text, visible tests, workflow review, and hidden evaluator are expected to align to this contract.

## Input Contract

The visible fixture JSON is the semantic input contract for this scoped task.

Required input groups used by the scoped contract:
- detector dimensions and sizes
  - `detector.spixels`
  - `detector.fpixels`
  - `detector.subpixel_size`
  - `detector.pixel_size`
  - `detector.close_distance`
- oversampling controls
  - `oversample.subpixel_steps`
  - `oversample.detector_thicksteps`
  - `oversample.oversample_omega`
  - `oversample.oversample_thick`
- geometry
  - `geometry.detector_origin`
  - `geometry.fast_axis`
  - `geometry.slow_axis`
  - `geometry.thickness`
  - `geometry.mu`
- source directions and source weights
  - `sources[*].direction`
  - `sources[*].weight`
  - `sources[*].wavelength` is present in fixtures but is not used by the current scoped reference math
- phi values
  - `phi_values` contribute only through iteration count in the current scoped reference math
  - individual phi angles are not used numerically by the current scoped reference math
- mosaic domains and mosaic weights
  - `mosaic_domains[*].weight`
  - `mosaic_domains[*].rotation_matrix` is present in fixtures but is not used by the current scoped reference math
- crystal defaults
  - `crystal.default_F` is a visible fixture input for the seed, but it is not part of the current scoped reference harness math

## Output Contract

Required output:
- a detector image tensor with shape `[spixels, fpixels]`
- tensor values must match the scoped hidden reference cases within the per-case tolerances

Optional debugging outputs are not part of the required public API for task completion.

## Included Math

The current scoped contract includes exactly these numerical components:
- detector/subpixel coordinate construction
- detector normal computation from fast/slow axes
- per-thickness-slice detector offset along the detector normal
- diffracted ray direction and airpath magnitude from detector sample position
- `omega_pixel` computation
- `capture_fraction` computation
- source weight contribution
- mosaic weight contribution
- iteration over source count, phi count, and mosaic-domain count
- accumulation into one scalar pixel intensity per detector pixel
- post-loop application of `capture_fraction` when `oversample_thick` is false
- post-loop application of `omega_pixel` when `oversample_omega` is false

## Excluded Math

The current scoped contract explicitly excludes these richer model terms:
- scattering vectors as numerical inputs to acceptance behavior
- polarization factors
- lattice factors
- unit-cell or structure-factor terms beyond the scoped harness defaults
- use of phi values as rotation angles in acceptance behavior
- use of mosaic rotation matrices in acceptance behavior
- broader physical effects from the larger `nanoBragg.c` subsystem

These may exist in the original source file or in future task expansions, but they are out of scope for the current demo contract.

## Normalization Rules

Normalization must match the scoped reference harness exactly:
- divide by `subpixel_steps * subpixel_steps`
- do not divide by detector thickness steps
- do not introduce extra averaging over source, phi, or mosaic axes beyond the reference behavior

## Oversample Semantics

Oversample behavior must match the scoped reference harness exactly:
- if `oversample_omega` is true, apply `omega_pixel` at the sub-sample contribution level
- if `oversample_omega` is false, accumulate first and apply one final `omega_pixel` factor after the loop
- if `oversample_thick` is true, apply `capture_fraction` at the sub-sample contribution level
- if `oversample_thick` is false, accumulate first and apply one final `capture_fraction` factor after the loop

The candidate implementation may tensorize these rules, but it must preserve this effective behavior.

## Restructuring Constraints

The implementation is expected to restructure the loop-heavy reference into a PyTorch-native form.

Required restructuring properties:
- detector pixel axes must be tensorized
- detector subpixel axes must be tensorized
- geometry preparation should be separated from accumulation where reasonable
- residual loops are acceptable only where they do not reintroduce detector-pixel or subpixel scalar iteration in Python

Allowed latitude:
- helper decomposition
- tensor broadcasting strategy
- exact module/function shape under `torch_port/`

Forbidden latitude:
- broadening the mathematical scope beyond this contract
- silently changing normalization
- inventing richer physics terms and treating them as required for correctness

## Relationship To Source Context

`src_c/nanoBragg.c` is included as visible source context, not as an invitation to expand the scoped mathematical contract beyond this document.

If the broader subsystem is desired later, the reference harness must be broadened first and this contract must be updated with it.
