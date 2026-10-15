# nanoBragg Reference Harness

Status: offline maintenance harness, scoped-simplified-harness-v1.
This produces expected tensors for the scoped nanoBragg accumulation task;
it does not establish parity with the complete external nanoBragg program.

`run_reference_case.py` compiles `reference_harness.c` with `cc`, loads the
shared library through `ctypes` and emits a float64 JSON tensor for one visible
fixture. `reference_types.h` defines its narrow input boundary.
`build_nanobragg_reference_cases.py` invokes that runner to write hidden
expected tensors during offline maintenance.

From the repository root with `cc` on PATH, inspect one visible fixture:

```bash
python scripts/demo/nanobragg_reference/run_reference_case.py examples/demo_task_nanobragg_accumulation_port/fixtures/visible/case_small.json
```

The builder also needs the project's Torch environment. Supply both `--case-id`
and `--output-path` to generate one temporary output without replacing the
tracked hidden corpus:

```bash
python scripts/demo/build_nanobragg_reference_cases.py --case-id case_small --fixture-path examples/demo_task_nanobragg_accumulation_port/fixtures/visible/case_small.json --output-path /tmp/nanobragg-expected-case-small.pt
```

The source anchor metadata refers to the separately available sibling
`nanoBragg/golden_suite_generator/nanoBragg.c`, intended accumulation slice
2839–3404. `extract_accumulation_slice.py` reports anchor/slice metadata;
its `--compile-check` only emits metadata and does not compile that source.
The runner compiles the scoped local harness, not an extracted full program,
and supplies no trace-tap or broader scientific-equivalence claim.

Keep this harness and hidden expected tensors outside both demo arms' staged
workspaces. Visible JSON fixtures may be shared; offline hidden-answer
maintenance is not trial-time execution and does not grant either arm reference
harness access. Omitting `--case-id` from the builder regenerates the full
hidden corpus and is not an inspection command.
