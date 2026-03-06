# nanoBragg hidden fixture corpus

This directory stores the hidden parity targets for the bounded nanoBragg accumulation demo task.

Schema:
- `cases.json`: metadata for each hidden case
- `expected_*.pt`: expected detector image tensors for each hidden case

Each case record contains:
- `case_id`
- `input_fixture_relpath`
- `expected_tensor_relpath`
- `rtol`
- `atol`
- optional `trace_taps`
- optional `notes`

`input_fixture_relpath` points at visible fixture files inside the candidate workspace. Hidden expected tensors remain outside the visible seed.
