# DSL Evolution Task 5 Execution Report

Implemented Task 5 (`v1.8` cycle guards): added loader/runtime support for workflow `max_transitions` and step `max_visits`, persisted `transition_count` and `step_visits` under the existing `state.json` schema, surfaced guard diagnostics in status snapshots, updated the normative/docs pages, and added `workflows/examples/cycle_guard_demo.yaml` plus targeted test coverage for loader gating, retry/skip semantics, resume persistence, and example runtime behavior.

Remaining risk: this tranche intentionally limits `max_visits` to top-level non-`for_each` steps until the later stable-ID work lands. Also, the current CLI smoke run with `--state-dir /tmp/dsl-evolution-cycle-guard-demo` still persisted the run under the workspace `.orchestrate/runs/` tree, so any future state-root contract work should verify that path behavior explicitly.

Verification:
- `pytest --collect-only tests/test_control_flow_foundations.py -q`
- `pytest tests/test_control_flow_foundations.py tests/test_loader_validation.py tests/test_state_manager.py tests/test_resume_command.py tests/test_retry_behavior.py -k "max_visits or max_transitions or control_flow" -v`
- `pytest tests/test_workflow_examples_v0.py -k cycle_guard -v`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/cycle_guard_demo.yaml --dry-run`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/cycle_guard_demo.yaml --state-dir /tmp/dsl-evolution-cycle-guard-demo`
- Persisted smoke-run evidence: `.orchestrate/runs/20260307T193413Z-8f4jdx/state.json` recorded `status: completed`, `transition_count: 7`, `step_visits.GuardLoop: 3`, `error.type: cycle_guard_exceeded` on `GuardLoop`, and `RecordGuardTrip.status: completed`.
