# nanoBragg hidden fixture corpus

This directory stores the hidden parity targets for the bounded nanoBragg accumulation demo task.

The authoritative scoped behavior definition for this demo task is:
- `examples/demo_task_nanobragg_accumulation_port/docs/tasks/nanobragg_accumulation_contract.md`

Current status:
- the evaluator contract expects reference-backed hidden outputs
- the corpus must record where those outputs came from
- regeneration is an offline maintenance workflow, not part of trial runtime

Schema:
- `cases.json`: metadata for each hidden case
- `expected_*.pt`: expected detector image tensors for each hidden case

Each case record contains:
- `case_id`
- `input_fixture_relpath`
- `expected_tensor_relpath`
- `rtol`
- `atol`
- `reference_method`
- `reference_source`
- `reference_snapshot` or `reference_commit`
- optional `trace_taps`
- optional `notes`

`input_fixture_relpath` points at visible fixture files inside the candidate workspace. Hidden expected tensors remain outside the visible seed.

Ground-truth policy:
- visible fixtures are shared with both trial arms
- hidden expected tensors must come from a trusted offline reference path
- hidden expectations must stay aligned to the scoped contract above
- hard-coded synthetic tensors in the builder are not acceptable
- builder provenance must be inspectable from `cases.json`

Regeneration workflow:
- use `scripts/demo/build_nanobragg_reference_cases.py`
- that builder should call an offline reference backend
- the backend should be a scoped `nanoBragg.c` reference harness or equivalent trusted reference implementation
