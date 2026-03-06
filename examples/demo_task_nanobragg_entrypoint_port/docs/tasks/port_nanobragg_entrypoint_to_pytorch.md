# Task: Port nanoBragg Entrypoint To PyTorch

Implement `torch_port.entrypoint.nanobragg_run` so that it matches the extracted `nanobragg_run` reference behavior derived from `src_c/nanoBragg.c`.

This task targets the high-level simulation path extracted from `main`, not a narrow detector kernel.

Requirements:
- use the visible fixtures under `fixtures/visible/`
- match the reference output tensor shape and numerical behavior on the provided cases
- keep the implementation scoped to this entrypoint task
- do not solve this as a wholesale scalar transliteration of the C loops
- use PyTorch tensor operations for the dominant detector/pixel work where feasible
- residual scalar loops are acceptable only where real data dependencies make batching impractical
