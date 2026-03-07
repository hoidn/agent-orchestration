Addressed the implementation-review follow-up for the DSL evolution work. Fixed five confirmed gaps: the loader now rejects structured refs that target unknown steps or invalid `outcome.*` fields before runtime; `self.steps.*` resolution no longer falls back to root state when a local scope is present but empty; undefined-variable command failures now normalize to `outcome = {class: pre_execution_failed, phase: pre_execution}` so typed routing can observe them correctly; nested v2.0 provider steps now look up `prompt_consumes` using their iteration-qualified consumer identity; and `max_visits` no longer suppresses execution-field exclusivity validation.

Added regression coverage for each reviewed bug: missing root-step refs, invalid normalized-outcome field refs, preserved runtime missing-value failures inside scoped refs, undefined-variable typed routing, self-scope isolation within `for_each`, nested provider consume injection, and `max_visits` plus command/provider exclusivity.

Verification run:
- `pytest --collect-only tests/test_typed_predicates.py tests/test_loader_validation.py tests/test_at63_undefined_variables.py tests/test_at65_loop_scoping.py tests/test_prompt_contract_injection.py -q` (`110 tests collected`)
- `pytest tests/test_typed_predicates.py -k "missing_root_step_exit_code_refs or unknown_outcome_members or missing_self_scope_value" -v` (`3 passed`)
- `pytest tests/test_loader_validation.py -k max_visits_does_not_bypass_execution_field_exclusivity -v` (`1 passed`)
- `pytest tests/test_at63_undefined_variables.py -k normalize_to_pre_execution -v` (`1 passed`)
- `pytest tests/test_at65_loop_scoping.py -k self_refs_do_not_fall_back_to_root_scope -v` (`1 passed`)
- `pytest tests/test_prompt_contract_injection.py -k iteration_scoped_consume_identity -v` (`1 passed`)
- `pytest tests/test_typed_predicates.py tests/test_loader_validation.py tests/test_at63_undefined_variables.py tests/test_at65_loop_scoping.py tests/test_prompt_contract_injection.py -v` (`110 passed`)
