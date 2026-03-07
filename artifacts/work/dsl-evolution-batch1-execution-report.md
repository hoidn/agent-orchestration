Implemented the first execution-plan batch (Tasks 1-3) for DSL evolution.

Changed:
- Added `version: "1.5"` first-class `assert` gates with dedicated `assert_failed` (`exit_code: 3`) runtime behavior and `on.failure.goto` recovery.
- Added `version: "1.6"` typed predicates (`artifact_bool`, `compare`, `all_of`, `any_of`, `not`), structured `ref:` resolution for `root.steps.<Step>...`, and normalized step `outcome` metadata.
- Added example workflows and smoke coverage for `assert_gate_demo.yaml` and `typed_predicate_routing.yaml`.
- Updated the normative specs and authoring/runtime guides to lock the rollout order, version gates, and the no-schema-bump boundary through Task 3.

Remaining risk:
- The typed-ref rollout is intentionally narrow: only root-scoped single-visit step refs are accepted. Later scoped refs, stable IDs, and nested execution identity are still pending.
- Full-repo `pytest` is not green because unrelated demo/nanobragg tests failed outside this batch (`tests/test_demo_nanobragg_entrypoint_reference_harness.py`, `tests/test_demo_task_nanobragg_alignment.py`) before the run was terminated.
- Future rollout tasks still need the planned schema/identity migration, scalar bookkeeping, cycle guards, and structured control-flow/call machinery described in the execution plan.

Verification run:
- `pytest tests/test_loader_validation.py -k "version or unknown or for_each" -v`
- `pytest tests/test_for_each_execution.py -k for_each -v`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration/.worktrees/dsl-evolution-batch1 python -m orchestrator run workflows/examples/for_each_demo.yaml --dry-run`
- `pytest tests/test_loader_validation.py tests/test_conditional_execution.py tests/test_runtime_step_lifecycle.py tests/test_observability_report.py -k "assert or gate" -v`
- `pytest tests/test_workflow_examples_v0.py -k assert_gate -v`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration/.worktrees/dsl-evolution-batch1 python -m orchestrator run workflows/examples/assert_gate_demo.yaml --dry-run`
- `pytest --collect-only tests/test_typed_predicates.py -q`
- `pytest tests/test_typed_predicates.py tests/test_loader_validation.py tests/test_conditional_execution.py tests/test_runtime_step_lifecycle.py tests/test_for_each_execution.py tests/test_observability_report.py -v`
- `pytest tests/test_workflow_examples_v0.py -k typed_predicate -v`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration/.worktrees/dsl-evolution-batch1 python -m orchestrator run workflows/examples/typed_predicate_routing.yaml --dry-run`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration/.worktrees/dsl-evolution-batch1 python -m orchestrator run workflows/examples/for_each_demo.yaml --dry-run`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration/.worktrees/dsl-evolution-batch1 python -m orchestrator run workflows/examples/assert_gate_demo.yaml --state-dir /tmp/dsl-evolution-assert-gate-demo`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration/.worktrees/dsl-evolution-batch1 python -m orchestrator run workflows/examples/typed_predicate_routing.yaml --state-dir /tmp/dsl-evolution-typed-predicate-demo`
- `pytest`
  - Targeted DSL/task coverage passed.
  - Full-suite run exposed unrelated demo failures before termination.
