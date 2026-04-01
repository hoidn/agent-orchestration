# nanoBragg Reference Harness

This directory holds the offline maintenance harness used to derive hidden
ground-truth tensors for the scoped nanoBragg accumulation task.

Scope:
- source file: `../nanoBragg/golden_suite_generator/nanoBragg.c`
- intended slice: lines 2839-3404
- purpose: regenerate hidden evaluator tensors from a trusted C reference

Non-goals:
- trial-time execution
- compiling or driving the full original `nanoBragg.c` program
- exposing this harness to either the direct or workflow demo arm

Current status:
- `extract_accumulation_slice.py` validates anchor coverage and reports slice metadata
- `reference_harness.c` is a stub interface scaffold only
- `reference_types.h` defines the initial narrow data boundary

Planned next step:
- implement a fixture-driven offline harness that emits detector-image tensors
  and optional trace taps for the visible JSON cases
