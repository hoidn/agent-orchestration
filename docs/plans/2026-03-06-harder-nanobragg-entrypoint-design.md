# Harder nanoBragg Entrypoint Design

## Decision

The harder task should not target the narrow detector-kernel slice around lines `2839-3404`.
That slice is too small once the requirement is "more than ~2000 reachable lines of C for the named entrypoint".

The viable target in `../nanoBragg/golden_suite_generator/nanoBragg.c` is a new extracted program-level entrypoint cut out of `main`, with helper calls preserved.

The benchmark should be:

- one named high-level call
- one broad call chain
- one output contract

It should not be:

- a kernel-only port
- a CLI-clone task
- a multi-entrypoint task

Recommended entrypoint name:

- `nanobragg_run`

## Source Scope

Recommended extracted body:

- start: `main` after CLI parsing and immediate file/header ingestion have resolved raw configuration, around lines `1138+`
- end: just before float/int/pgm/noise image writing and final process exit around lines `3474+`

Practical extraction span:

- setup/default resolution and detector convention handling
- vector normalization and derived geometry
- source generation/materialization
- crystal/cell/HKL preparation
- interpolation / reciprocal-space setup
- detector accumulation sweep
- intensity statistics needed to finalize the float image

This extracted body should be treated as the functional translation target for almost the whole program.
The task is still verified through one entrypoint call, but the reachable logic should cover most of the substantive simulation code in `nanoBragg.c`.

Do not include:

- CLI argument parsing
- file-path based program configuration
- float/int/pgm/noise image writing
- progress meter / printf-heavy reporting as part of the public contract
- Poisson noise simulation

## Why This Scope

This is the smallest defensible entrypoint that still satisfies the "substantial reachable C" requirement.

The earlier accumulation-only task depended on too much precomputed state:

- detector conventions already resolved
- source arrays already materialized
- crystal orientation already resolved
- HKL/default-F behavior already collapsed

That made the real task a kernel port, not a substantial port of the program's simulation path.

By extracting the post-parse simulation path from `main`, the task becomes:

- one named high-level entrypoint
- one large C control flow region
- one call chain that reaches most of the substantive program logic
- one unambiguous output: detector float image

This gives a clear success condition without a handholdy public contract.

## Public Entrypoint Contract

The public task should name only:

- the C entrypoint: `nanobragg_run`
- the source file: `src_c/nanoBragg.c`
- the approximate extracted source region: "the extracted post-parse simulation path from `main` covering most of the program's simulation logic"
- the required PyTorch target entrypoint, for example:
  - `torch_port.entrypoint.nanobragg_run`
- the required output:
  - detector float image for the provided fixture

The task text should not restate the algorithm in prose.

## Harness Boundary

The standalone C reference harness should expose one callable function with structured inputs, for example:

```c
int nanobragg_run(
    const NBInput *input,
    NBOutput *output
);
```

`NBInput` should contain raw experiment inputs, not precomputed kernel tensors.
That means the fixture format should carry enough information for the harness to execute the extracted setup path itself.

Inputs should cover at least:

- detector dimensions and ROI
- detector convention / vectors / distances / pixel size
- oversampling and detector-thickness settings
- beam/source description
- phi / oscillation / mosaic settings
- cell/orientation description
- HKL/default-F description
- crystal-size / shape / interpolation-relevant settings

Outputs should include:

- `floatimage`
- output shape metadata
- optional trace taps for a few fixed internal scalars or pixels

The harness should be the only place where "full-file translation" is operationalized.
The public benchmark remains a single entrypoint-matching task.

## Hidden Probe Principle

Hidden scoring should only use probes that are naturally observable from the task shape.

Acceptable probe targets:

- selected output pixels or output regions
- semantically stable intermediate quantities only when they are natural consequences of the extracted entrypoint contract itself
- quantities that can be measured from the extracted reference call chain without adding bespoke debug-only control flow

Avoid:

- hidden probes that require the candidate to expose ad hoc instrumentation APIs
- probes that only make sense if the agent has followed one preferred decomposition
- public task wording that effectively names the hidden probes in solution-shaped detail

If a probe site would require special-purpose candidate instrumentation or would only be practical under one preferred decomposition, that is a sign the task boundary should be adjusted instead of the public task being made more handholdy.

## Fixture Philosophy

Visible fixtures should be in-memory experiment descriptions for the entrypoint, not prose contracts.

They should be explicit enough that the harness does not have to guess parameters, but they should not encode the reference decomposition.

The agent should infer behavior from:

- the named entrypoint
- the source region
- the visible fixtures
- the visible smoke tests

## Task Statement Shape

Recommended user-facing task statement:

"Port the extracted `nanobragg_run` entrypoint from `src_c/nanoBragg.c` into `torch_port.entrypoint.nanobragg_run` using PyTorch. Match the reference entrypoint's detector float-image outputs on the provided fixtures. This entrypoint is intended to cover most of the substantive simulation path in `nanoBragg.c`; keep the port scoped to that extracted call chain and avoid reimplementing unrelated CLI or file-writing behavior."

## Implications For The Rest Of The Plan

This changes the implementation plan in three ways:

1. The reference harness must wrap a large extracted `main` path that reaches most of the substantive simulation logic, not just the detector accumulation loop.
2. Fixtures must carry richer raw experiment inputs.
3. The new seed should be treated as a program-level entrypoint port, not a kernel port.
4. Hidden scoring probes should be limited to naturally measurable outputs or stage boundaries, not bespoke debug hooks.
