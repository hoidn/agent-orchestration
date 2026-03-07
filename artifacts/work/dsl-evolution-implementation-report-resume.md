Addressed the remaining 2026-03-07 implementation-review findings for the DSL evolution work.

Closed four confirmed gaps:
- Resume restart detection now checks persisted `state["for_each"]` bookkeeping before treating a top-level loop as terminal, so a partial `steps.<Loop>` summary plus `current_index` resumes at the first incomplete iteration instead of replaying completed work or skipping unfinished work.
- Structured-ref validation now applies the active scope's multi-visit catalog to `self.steps.*`, so top-level v2.0 `self.steps.<Loop>...` refs can no longer bypass the first-tranche multi-visit rejection that already applied to `root.steps.*`.
- Provider parameter substitution now prefers the execution context's scoped `steps` namespace when present, so `${steps.StepA.output}` inside `for_each` provider steps resolves against the current iteration rather than root state.
- Provider preparation failures (`substitution_error`, `validation_error`, `missing_secrets`, `provider_not_found`, and `provider_preparation_failed`) now normalize to `outcome.phase = pre_execution`, `outcome.class = pre_execution_failed`, and `retryable = false`, restoring the typed failure-routing contract for provider setup errors.

Added regression coverage for:
- real `resume_workflow()` recovery from a partial loop state that includes incremental `steps.<Loop>` summary entries, persisted `for_each` bookkeeping, and a stale `current_step`
- top-level v2.0 `self.steps.*` refs targeting provably multi-visit steps
- loop-scoped provider parameter substitution against `${steps.<Nested>.output}`
- typed routing over provider pre-execution failures

Files changed:
- `orchestrator/loader.py`
- `orchestrator/workflow/executor.py`
- `tests/test_resume_command.py`
- `tests/test_typed_predicates.py`
- `tests/test_for_each_execution.py`
- `tests/test_runtime_step_lifecycle.py`

Verification run:
- `pytest --collect-only tests/test_resume_command.py tests/test_typed_predicates.py tests/test_for_each_execution.py tests/test_runtime_step_lifecycle.py -q` (`46 tests collected`)
- `pytest tests/test_resume_command.py -k incremental_summary -v` (`1 passed`)
- `pytest tests/test_typed_predicates.py -k top_level_self_refs_to_multi_visit -v` (`1 passed`)
- `pytest tests/test_for_each_execution.py -k iteration_scope -v` (`1 passed`)
- `pytest tests/test_runtime_step_lifecycle.py -k provider_pre_execution_failures_normalize -v` (`1 passed`)
- `pytest tests/test_resume_command.py tests/test_typed_predicates.py tests/test_for_each_execution.py tests/test_runtime_step_lifecycle.py -v` (`46 passed`)
- `pytest tests/test_loader_validation.py -k "step_id or scoped_ref or max_visits_does_not_bypass_execution_field_exclusivity" -v` (`5 passed`)
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/for_each_demo.yaml --dry-run` (`[DRY RUN] Workflow validation successful`)
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/typed_predicate_routing.yaml --dry-run` (`[DRY RUN] Workflow validation successful`)
