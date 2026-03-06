# nanoBragg source guidance

This seed includes the full `nanoBragg.c` source file as visible reference material. The task is a bounded subsystem port, not a transliteration exercise.

The authoritative acceptance target is:
- `docs/tasks/nanobragg_accumulation_contract.md`

Focus region:
- outer detector subpixel loop near line 2839
- inner detector subpixel loop near line 2887
- `omega_pixel` and `capture_fraction` setup near lines 2916-2981
- source-count iteration near lines 2983-3040
- final accumulation into `floatimage[imgidx]` near lines 3364-3404

In scope:
- detector subpixel coordinate construction
- solid-angle and detector-thickness capture terms
- source-weight and mosaic-weight accumulation behavior defined by the scoped contract
- the final accumulated detector image tensor for the scoped fixture corpus

Out of scope:
- the rest of `nanoBragg.c`
- CLI parsing
- image file writing
- noise generation
- serialization
- unrelated post-processing loops after the main accumulation path

Use this file to understand the legacy computation shape and factor ordering. Do not try to mirror every local variable one-for-one in PyTorch, and do not broaden the implementation beyond the scoped contract.
