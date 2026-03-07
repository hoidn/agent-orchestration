Implemented Task 6 of the DSL evolution plan: added v2.0 authored step `id` validation, stable internal `step_id` assignment, scoped typed refs (`root`/`self`/`parent`), state schema bump to `2.0`, resume rejection for pre-v2.0 state, and qualified `for_each` lineage/freshness identities. Updated runtime/state/report plumbing to persist `step_id`, kept legacy `steps.<Name>` loop substitution behavior unchanged for pre-v2.0 workflows, and documented the new boundary in specs/docs.

Remaining risk: nested execution support is still limited to the existing `for_each` model, with presentation-oriented `state.steps` keys retained for compatibility while durable lineage moved to `step_id`; there is intentionally no upgrader for pre-v2.0 state; and later planned tranches (`inputs`/`outputs`, structured control flow, `call`) still need to build on this foundation.

Verification run:
- `pytest tests/test_loader_validation.py tests/test_control_flow_foundations.py tests/test_state_manager.py tests/test_resume_command.py -k 'step_id or scoped_ref or schema' -v`
- `pytest tests/test_artifact_dataflow_integration.py tests/test_for_each_execution.py tests/test_at65_loop_scoping.py -k 'legacy or qualified or lineage or freshness or for_each or loop_scoping' -v`
- `pytest --collect-only tests/test_loader_validation.py tests/test_state_manager.py tests/test_resume_command.py tests/test_artifact_dataflow_integration.py tests/test_at65_loop_scoping.py -q`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/for_each_demo.yaml --dry-run`
- `pytest tests/test_loader_validation.py tests/test_state_manager.py tests/test_resume_command.py tests/test_artifact_dataflow_integration.py tests/test_at65_loop_scoping.py -v`
