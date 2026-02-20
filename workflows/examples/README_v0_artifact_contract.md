# v0 Artifact-Contract Prototype Runbook

This runbook documents the prototype workflows that use deterministic file-based output contracts.

## Workflows

- `workflows/examples/backlog_plan_execute_v0.yaml`
  - Pattern: backlog item selection -> plan draft -> plan execution -> optional review loop.
- `workflows/examples/test_fix_loop_v0.yaml`
  - Pattern: run tests -> gate on failure count -> fix -> retry until pass/max cycles.
- `workflows/examples/unit_of_work_plus_test_fix_v0.yaml`
  - Pattern: perform unit-of-work -> run tests -> fix loop.

## Deterministic Handoff Contract

- Each phase writes required artifacts to files under `state/` or `artifacts/`.
- Each producing step declares `expected_outputs` with explicit `name`.
- Downstream logic consumes values from `steps.<Step>.artifacts.<name>`.

## Verification Commands

```bash
cd ~/Documents/agent-orchestration
pytest tests/test_loader_validation.py -k "expected_outputs or inject_output_contract" -v
pytest tests/test_output_contract.py -v
pytest tests/test_workflow_output_contract_integration.py -v
pytest tests/test_prompt_contract_injection.py -v
pytest tests/test_workflow_examples_v0.py -v
```

Runtime smoke proof:

```bash
cd ~/Documents/agent-orchestration
pytest tests/test_workflow_examples_v0.py -k runtime -v
```

Optional dry-run check:

```bash
cd ~/Documents/agent-orchestration
orchestrate run workflows/examples/backlog_plan_execute_v0.yaml --dry-run
```

## Known Limitations (v0)

- Prompt-level behavior is still prompt-authored; this prototype only enforces deterministic file outputs.
- Loop control uses existing `on.*.goto` and shell gates (no new control-flow DSL primitives yet).
- Exit-code taxonomy for contract failures is currently implementation-defined; consumers should gate on non-zero plus `error.type == "contract_violation"`.
