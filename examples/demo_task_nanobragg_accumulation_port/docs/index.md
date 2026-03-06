# Workspace Index

Start here.

## Key Files

- `state/task.md`: canonical task description injected at runtime
- `docs/tasks/port_nanobragg_accumulation_to_pytorch.md`: canonical task fixture for this seed
- `docs/tasks/nanobragg_accumulation_contract.md`: authoritative scoped behavior contract for this seed
- `src_c/nanoBragg.c`: legacy source file containing the scoped subsystem
- `src_c/README.md`: guidance on which `nanoBragg.c` regions matter for this task
- `torch_port/`: PyTorch target area
- `fixtures/visible/`: visible smoke-input fixtures for local checks
- `tests/test_smoke_accumulation.py`: visible smoke-check entrypoint
- `docs/dev_guidelines.md`: local engineering rules
- `docs/plans/templates/`: optional planning and review aids
- `artifacts/`: execution, check, and review outputs
- `state/`: workflow state and task artifacts

## Expectations

- Read the injected task first. If it mirrors the canonical task fixture, follow the injected file.
- Use `docs/tasks/nanobragg_accumulation_contract.md` as the authoritative mathematical scope for the task.
- The trial environment is assumed to already provide `torch`; verify availability with `python -c "import torch; print(torch.__version__)"`.
- Keep the task bounded to the documented detector pixel accumulation subsystem.
- Visible verification command is `pytest -q`.
- Visible smoke checks are intentionally incomplete, so use them as a floor rather than proof that all parity requirements are satisfied.
