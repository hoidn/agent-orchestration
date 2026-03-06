# nanoBragg Entrypoint Hidden Fixtures

This directory stores hidden evaluator metadata, hidden-only input fixtures, and expected outputs for the `nanobragg_run` benchmark.

Each hidden case records:

- the fixture origin (`workspace` visible smoke fixture or evaluator-owned hidden input)
- the fixture path relative to that origin
- the expected output tensor path
- output shape metadata
- output probe sites used in score computation
- provenance for the reference source used to generate the tensor
