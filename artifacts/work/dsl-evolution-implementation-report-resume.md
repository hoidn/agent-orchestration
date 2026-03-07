Addressed the remaining implementation-review findings for the DSL evolution work.

Closed two confirmed gaps:
- `for_each` now persists durable loop bookkeeping in `state["for_each"]` and incrementally writes the loop summary array during execution, so resume restarts from the first incomplete iteration instead of replaying completed work.
- Structured ref parsing now matches the full step selector against the available scope instead of assuming the selector is the third dot-separated token, so v2.0 typed refs can target valid step names such as `Build.v1` while still rejecting unknown steps and invalid `outcome.*` members at load time.

Added regression coverage for:
- persisted `for_each` bookkeeping after a normal loop completes
- real `resume_workflow()` recovery of a partially completed loop using persisted bookkeeping
- typed predicate refs against dotted step names

Verification run:
- `pytest --collect-only tests/test_for_each_execution.py tests/test_resume_command.py tests/test_typed_predicates.py -q` (`37 tests collected`)
- `pytest tests/test_for_each_execution.py -k persists_loop_bookkeeping_state -v` (`1 passed`)
- `pytest tests/test_resume_command.py -k skips_completed_iterations_using_bookkeeping -v` (`1 passed`)
- `pytest tests/test_typed_predicates.py -k target_step_names_containing_dots -v` (`1 passed`)
- `pytest tests/test_typed_predicates.py tests/test_for_each_execution.py tests/test_resume_command.py -v` (`37 passed`)
- `pytest tests/test_loader_validation.py -k "step_id or scoped_ref or max_visits_does_not_bypass_execution_field_exclusivity" -v` (`5 passed`)
- `pytest tests/test_artifact_dataflow_integration.py tests/test_at65_loop_scoping.py tests/test_prompt_contract_injection.py -k "qualified or lineage or loop_scoping or iteration_scoped_consume_identity" -v` (`11 passed`)
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/for_each_demo.yaml --dry-run` (`[DRY RUN] Workflow validation successful`)
