# Workspace Index

Start here.

## Key Files

- `state/task.md`: canonical task description injected at runtime
- `docs/tasks/port_nanobragg_entrypoint_to_pytorch.md`: canonical task fixture for this seed
- `src_c/nanoBragg.c`: legacy C source containing the reference call chain
- `src_c/README.md`: guidance on where the entrypoint lives in the source
- `fixtures/visible/`: visible smoke-input fixtures for local checks
- `torch_port/entrypoint.py`: PyTorch target entrypoint
- `tests/test_smoke_entrypoint.py`: visible smoke-check entrypoint
- `docs/dev_guidelines.md`: local engineering rules

## Expectations

- Read the injected task first. If it mirrors the canonical task fixture, follow the injected file.
- The benchmark target is the `nanobragg_run` program-level call chain derived from `nanoBragg.c`'s `main` simulation path.
- Visible verification command is `pytest -q`.
- Visible smoke checks are intentionally incomplete.
