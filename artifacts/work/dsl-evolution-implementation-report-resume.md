Updated Task 6 after implementation review. Fixed three confirmed gaps: `for_each` loop bodies now execute nested `assert`, `set_scalar`, `increment_scalar`, and `wait_for` steps through a real dispatcher with scoped typed-ref evaluation; compiler-generated internal `step_id` tokens are deduplicated within each lexical sibling scope; and the loader now rejects `parent.steps.*` structured refs that target provably multi-visit parent/root steps. Added regression coverage for the compiler-token collision case, the ambiguous `parent.steps.*` cycle case, and runtime execution of nested v2.0 loop steps that combine scalar bookkeeping, `wait_for`, and scoped `assert`.

Remaining risk: nested execution is still limited to the current `for_each` model; compiler-generated ids are now unique but only authored `id` values provide source-stable identities across broader structural edits; there is still no upgrader for pre-v2.0 state; and later tranches (`inputs`/`outputs`, structured control flow, `call`) still need to build on this foundation.

Verification run:
- `pytest --collect-only tests/test_loader_validation.py tests/test_at65_loop_scoping.py -q` (`79 tests collected`)
- `pytest tests/test_loader_validation.py -k "compiler_generated_step_ids_disambiguate_colliding_names or v2_parent_refs_reject_multi_visit_targets" -v` (`2 passed`)
- `pytest tests/test_at65_loop_scoping.py -k "v2_nested_steps_execute_with_scoped_refs_inside_for_each" -v` (`1 passed`)
- `pytest tests/test_loader_validation.py tests/test_control_flow_foundations.py tests/test_state_manager.py tests/test_resume_command.py -k 'step_id or scoped_ref or schema' -v` (`8 passed, 90 deselected`)
- `pytest tests/test_artifact_dataflow_integration.py tests/test_for_each_execution.py tests/test_at65_loop_scoping.py -k 'legacy or qualified or lineage or freshness or for_each or loop_scoping or nested_steps_execute' -v` (`24 passed, 11 deselected`)
