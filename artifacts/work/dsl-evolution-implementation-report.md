Implemented Task 4 of the DSL evolution plan: added `v1.7` scalar bookkeeping with first-class `set_scalar` and `increment_scalar` step forms, loader/runtime support for emitting local scalar artifacts, `publishes.from` integration for those outputs, a runnable example workflow, and matching spec/acceptance updates.

Remaining risk is intentionally bounded to later tranches: bookkeeping still depends on the current top-level name-keyed artifact lineage/state model, `increment_scalar` reads the latest published version rather than any future scoped/stable-ID identity surface, and cycle guards / workflow signatures / structured control flow are still unimplemented.

Verification run:
- `pytest --collect-only tests/test_scalar_bookkeeping.py -q`
- `pytest tests/test_scalar_bookkeeping.py tests/test_loader_validation.py tests/test_artifact_dataflow_integration.py tests/test_runtime_step_lifecycle.py -v`
- `pytest tests/test_workflow_examples_v0.py -k scalar_bookkeeping -v`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/scalar_bookkeeping_demo.yaml --dry-run`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/scalar_bookkeeping_demo.yaml --state-dir /tmp/dsl-evolution-scalar-bookkeeping-demo`
