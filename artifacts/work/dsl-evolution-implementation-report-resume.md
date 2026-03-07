Addressed the remaining 2026-03-07 implementation-review findings for the DSL evolution work.

Closed three confirmed gaps from the latest review pass:
- Legacy `assert.equals` inside nested `for_each` steps now builds substitution variables from the loop-scoped `steps` namespace when present, so `${steps.StepA.output}` resolves against the current iteration instead of the root workflow state.
- Structured-ref validation now rejects refs that target `for_each` summary steps at load time, instead of accepting `self.steps.<Loop>.exit_code` / `outcome.*` and deferring the failure until runtime when the stored value is a list, not a step-result mapping.
- `${env.*}` validation now applies to legacy `assert` condition surfaces (`equals`, `exists`, `not_exists`) in the same way it already applied to command/provider and legacy `when` substitution fields.

Regression coverage added for:
- loop-scoped legacy `assert.equals(left=${steps.StepA.output}, right=${item})` inside `for_each`
- loader rejection for `self.steps.<Loop>.exit_code` when `<Loop>` is a `for_each` step summary
- loader rejection for `assert.equals.left: ${env.SECRET}`

Files changed in this pass:
- `orchestrator/loader.py`
- `orchestrator/workflow/executor.py`
- `tests/test_for_each_execution.py`
- `tests/test_loader_validation.py`
- `tests/test_typed_predicates.py`

Verification run:
- `pytest --collect-only tests/test_for_each_execution.py tests/test_typed_predicates.py tests/test_loader_validation.py -q` (`100 tests collected`)
- `pytest tests/test_for_each_execution.py -k assert_equals_resolves_steps_against_iteration_scope -v` (`1 passed`)
- `pytest tests/test_typed_predicates.py -k refs_to_for_each_summary_steps -v` (`1 passed`)
- `pytest tests/test_loader_validation.py -k assert_equals_rejects_env_namespace -v` (`1 passed`)
- `pytest tests/test_loader_validation.py tests/test_for_each_execution.py tests/test_typed_predicates.py tests/test_runtime_step_lifecycle.py -q` (`108 passed in 2.28s`)
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/assert_gate_demo.yaml --dry-run` (`[DRY RUN] Workflow validation successful`)
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/typed_predicate_routing.yaml --dry-run` (`[DRY RUN] Workflow validation successful`)
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/for_each_demo.yaml --dry-run` (`[DRY RUN] Workflow validation successful`)
