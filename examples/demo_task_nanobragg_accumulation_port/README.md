# Demo Task Seed: nanoBragg Accumulation Port

This task-specific seed extends the generic demo scaffold with a substantially harder porting problem: a bounded PyTorch translation of a numerically meaningful subsystem from `nanoBragg.c`.

Design style:
- preserve the direct-vs-workflow comparison shape from the smaller demo seeds
- expose a real legacy scientific source file rather than a toy Python reference
- require restructuring into clear PyTorch helpers instead of line-for-line transliteration
- keep the visible checks intentionally incomplete so hidden parity still matters

Task shape:
- visible C source material under `src_c/`
- target PyTorch module under `torch_port/`
- visible smoke fixtures under `fixtures/visible/`
- canonical task description under `docs/tasks/`

Environment expectation:
- the trial environment is assumed to already provide `torch`
- verify availability with `python -c "import torch; print(torch.__version__)"`
- visible verification command is `pytest -q`

The hidden evaluator is intentionally not included in this tree.
